"""
Usage:
    sii pdf [options] list formats
    sii pdf [options] list mediums
    sii pdf [options] list printers
    sii pdf [options] create tex [<outfile>] <infile>...
    sii pdf [options] create pdf [--progress] [--suffixed | <outfile>] <infile>...
    sii pdf [options] print <printer> <infile>...

Options:
    --format <format>  # Format to output the file to. Available are 'tex' and 'pdf'. [default: pdf]
    --medium <medium>  # Paper size to use. Available are 'carta', 'oficio' and 'thermal80mm'. [default: carta]
    --cedible          # If "cedible" declaration form should be included [default: false]

    -p --progress  # Output progress. [default: false]

Notes:
    Listing printers lists the available local printers as available/visible to the systems 'lp'.

    Creating TeX's you have to consider for the resources to be written by side of the .tex file.
    You have to account for that, since it can become messy. It is recomended to use this with a
    directory per document approach. That is also what makes it mutually exclusive from --suffixed.

    Output will –unless otherwise explicitly specified– default to stdout.
"""
import base64
import os.path as path

import docopt

from sii.lib       import printing
from sii.lib.lib   import xml
from sii.lib.types import CompanyPool

from .helpers import print_stderr, read_xml


def handle(config, argv):
    args = docopt.docopt(__doc__, argv=argv)

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
    template = None
    output   = None

    counter = 0
    for source_path in args['<infile>']:
        tree = read_xml(source_path)
        dte  = xml.wrap_xml(tree)

        dte_type = int(dte.Documento.Encabezado.IdDoc.TipoDTE)
        dte_rut  = int(str(dte.Documento.Encabezado.Emisor.RUTEmisor).split('-')[0])

        company_pool = CompanyPool.from_file(config.static.companies)

        if args['--cedible'] and dte_type in (56, 61):
            raise SystemExit("NC and ND are not subject to the argument --cedible. Will not proceed...")

        # Generate TeX
        if args['--medium'] not in ('carta', 'oficio', 'thermal80mm'):
            raise SystemExit("Unknown medium to generate printable template for: {0}".format(args['--medium']))

        template, resources = printing.create_template(tree, company_pool, args['--medium'], cedible=args['--cedible'])

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

            if args['--progress']:
                print_stderr(
                    "[{0}/{1}] Created PDF from {2}".format(
                        counter + 1,
                        len(args['<infile>']),
                        source_path)
                )

            if args['--suffixed']:
                basepath = path.basename(source_path).split('.')[0]
                if args['--cedible']:
                    sink_path = basepath + '_cedible.pdf'
                else:
                    sink_path = basepath + '.pdf'

                with open(sink_path, 'wb') as fh:
                    fh.write(output)
            elif args['<outfile>']:
                with open(args['<outfile>'], 'wb') as fh:
                    fh.write(output)
            else:
                print(output)
        else:
            raise RuntimeError("Conditional Fallthrough")

        counter += 1


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
