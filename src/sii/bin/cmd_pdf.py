"""
Usage:
    sii pdf [options] list formats
    sii pdf [options] list mediums
    sii pdf [options] list printers
    sii pdf [options] create tex [<outfile>] [-] | <infile>...
    sii pdf [options] create pdf [--progress] [--suffixed | --generate | <outfile>] ([-] | <infile>...)
    sii pdf [options] print <printer> <infile>...

Options:
    # PDF and TEX Options
    --format <format>  # Format to output the file to. Available are 'tex' and 'pdf'. [default: pdf]
    --medium <medium>  # Paper size to use. Available are 'carta', 'oficio' and 'thermal80mm'. [default: carta]
    --extern           # Specify whether we own the document or whether it was received from a 3d-party/extern/provider.
    --cedible          # If "cedible" declaration form should be included [default: false]
    --draft            # Include a DRAFT disclaimer on the document.

    -j --jobs <n>  # Number of jobs to run concurrently. Provided with (<n> == 0), CPU count - 1 will be used.

    -p --progress  # Output progress.
    -v --verbose   # Be talkative about what is going on.

Notes:
    Listing printers lists the available local printers as available/visible to the systems 'lp'.

    Creating TeX's you have to consider for the resources to be written by side of the .tex file.
    You have to account for that, since it can become messy. It is recomended to use this with a
    directory per document approach. That is also what makes it mutually exclusive from --suffixed.

    Output will –unless otherwise explicitly specified– default to stdout.
"""
import sys
import base64
import signal
import os.path as path

import queue
import threading as th
import multiprocessing as mp

import docopt

from sii.lib       import printing
from sii.lib.lib   import xml
from sii.lib.types import CompanyPool

from .helpers import print_stderr, read_xml


def handle(config, args, argv):
    subargs = docopt.docopt(__doc__, argv=argv)
    args.update(subargs)

    if args['list']:
        handle_list(args, config)
    elif args['create']:
        handle_create(args, config)
    elif args['print']:
        handle_print(args, config)
    else:
        raise RuntimeError("Conditional Fallthrough")


def handle_list(args, config):
    if args['formats']:
        print("Available Output Formats:")

        for fmt in printing.output_formats():
            print(fmt)
    elif args['mediums']:
        for mdm in ('thermal80mm', 'carta', 'oficio'):  # TODO real library support
            print(mdm)
    elif args['printers']:
        for printer in printing.list_printers():
            print(printer)
    else:
        raise RuntimeError("Conditional Fallthrough")


def handle_create(args, config):
    sources = []
    if args['<infile>']:
        for pth in args['<infile>']:
            with open(pth, 'rb') as fh:
                buff = fh.read()
            sources.append((pth, buff))
    else:
        for bytebuff in sys.stdin.buffer:
            sources.append(('stdin', bytebuff))

        if args['--suffixed']:
            raise SystemExit("Cannot --suffix if input comes from stdin!")

    if not args['--extern']:
        company_pool = CompanyPool.from_file(config.static.companies)
    else:
        company_pool = None

    # Determine job count
    if args['--jobs']:
        worker_count = int(args['--jobs']) if int(args['--jobs']) > 0 else mp.cpu_count() - 1 or 1
    else:
        worker_count = 1

    # Create and feed job queue
    q_in  = queue.Queue()
    q_out = queue.Queue()

    for job_id, source in enumerate(sources):
        q_in.put((args, company_pool, source, job_id + 1))

    for _ in range(worker_count):
        q_in.put(None)  # sentinel to finish for each of the workers

    # Set SIGINT handler to close the queue
    # signal.signal(signal.SIGINT,  lambda sig, stack: q_in.close())
    # signal.signal(signal.SIGTERM, lambda sig, stack: q_in.close())

    # Spawn and start jobs
    workers = {pid: th.Thread(target=_handle_create_worker, args=(pid, q_in, q_out)) for pid in range(worker_count)}
    for pid, worker in workers.items():
        if args['--debug']:
            print_stderr("Spawning Worker with PID <{0}>".format(pid))

        worker.start()

    # Wait for workers to finish while handling their exceptions
    while workers:
        pid, *event = q_out.get()

        if not event or event[0] is None:
            worker = workers.pop(pid)
            worker.join()

            if args['--debug']:
                print_stderr("Releasing Worker with PID <{0}>".format(pid))
        else:
            jid, exc = event

            if args['--debug']:
                print_stderr("Worker <{0}> has encountered an error on job <{1}>: {2}".format(pid, jid, str(exc)))


def _handle_create_worker(pid, q_in, q_out):
    while True:
        try:
            job = q_in.get()
        except OSError:      # parent says abort by closing the queue
            break
        else:
            if job is None:  # got a "finish" sentinel
                break

        args, cmpny_pool, source, jid = job
        pth, bytebuff = source

        try:
            dte  = xml.load_xml(bytebuff)
            tree = xml.dump_etree(dte)

            dte_type = int(dte.Documento.Encabezado.IdDoc.TipoDTE)
            dte_id   = int(dte.Documento.Encabezado.IdDoc.Folio)
            dte_rut  = int(str(dte.Documento.Encabezado.Emisor.RUTEmisor).split('-')[0])

            if args['--cedible'] and dte_type in (56, 61):
                raise SystemExit("NC and ND are not subject to the argument --cedible. Will not proceed...")

            if args['--medium'] not in ('carta', 'oficio', 'thermal80mm'):
                raise SystemExit("Unknown medium to generate printable template for: {0}".format(args['--medium']))

            template, resources = printing.create_template(
                dte_xml = tree,
                medium  = args['--medium'],
                company = cmpny_pool,
                cedible = args['--cedible'],
                draft   = args['--draft']
            )

            if args['--verbose']:
                print_stderr(
                    "[{0}/{1}] Generated PDF{2} for {3}"
                    .format(jid, len(args['<infile>']), " (cedible)" if args['--cedible'] else "", pth)
                )

            if args['tex']:
                if args['<outfile>']:
                    # Write .tex template file
                    with open(args['<outfile>'], 'w') as fh:
                        fh.write(template)

                    # Write template resources right beside the .tex file
                    basepath = path.dirname(args['<outfile>'])
                    for res in resources:
                        res_path = path.join(basepath, res.filename)

                        with open(res_path, 'wb') as fh:
                            fh.write(res.data)
            elif args['pdf']:
                b64pdf = printing.tex_to_pdf(template, resources)
                output = base64.b64decode(b64pdf)

                if args['--suffixed']:
                    basepath = path.basename(pth).split('.')[0]
                    if args['--cedible']:
                        sink_path = basepath + '_cedible.pdf'
                    else:
                        sink_path = basepath + '.pdf'

                    with open(sink_path, 'wb') as fh:
                        fh.write(output)
                elif args['--generate']:
                    outpth = "{0}_{1}_{2}{3}.pdf".format(dte_rut, dte_type, dte_id, "_cedible" if args['--cedible'] else "")

                    with open(outpth, 'wb') as fh:
                        fh.write(output)
                elif args['<outfile>']:
                    with open(args['<outfile>'], 'wb') as fh:
                        fh.write(output)
                else:
                    print(output)
            else:
                raise RuntimeError("Conditional Fallthrough")

        except Exception as exc:
            print_stderr(
                "[{0}/{1}] Processing PDF{2} for {3} FAILED: {4}"
                .format(jid, len(args['<infile>']), " (cedible)" if args['--cedible'] else "", pth, str(exc))
            )

            if args['--debug']:
                raise

            q_out.put((pid, jid, exc))

    q_out.put((pid, None))  # sentinel that i'm on my way out


def handle_print(args, config):
    lp_printers = printing.list_printers()

    sel_printer   = args['<printer>']
    sel_documents = args['<infile>']

    if sel_printer not in lp_printers:
        raise SystemExit("No such printer: {0}".format(sel_printer))
    else:
        for pth in sel_documents:
            exists = path.isfile(pth)
            ext    = path.splitext(pth)[-1]

            if not exists:
                raise SystemExit("Could not find provided file: <{0}>".format(pth))

            if ext == '.pdf':
                printing.print_pdf_file(pth, sel_printer)
            elif ext == '.tex':
                with open(pth, 'r') as fh:
                    tex_buff = fh.read()
                    printing.print_tex(tex_buff, sel_printer)
            else:
                raise SystemExit("Unknown file extension: <{0}>".format(ext))
