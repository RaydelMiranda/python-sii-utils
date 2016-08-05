"""
Usage:
    sii xml [options] read              <infile>...
    sii xml [options] bundle dte        [--inplace | --suffixed] <infile>...
    sii xml [options] bundle enviodte   (--sii | --exchange) <outfile> <infile>...
    sii xml [options] bundle lv         <outfile> <infile>...
    sii xml [options] unbundle enviodte [--inplace] [--generate] <envio>...
    sii xml [options] gen doc ack       <infile> <outfile>
    sii xml [options] gen doc ok        <infile> <outfile>
    sii xml [options] gen merch ack     <infile> <outfile>
    sii xml [options] sign              [--all] [--inplace | --suffixed | <outfile>] <infile>...
    sii xml [options] verify signature  <infile>...
    sii xml [options] verify schema     [--xsd=<file>] <infile>...
    sii xml [options] void doc          <outfile> <infile>...

Options:
    --inplace   # Will modify the same file it read with the processed output.
    --suffixed  # Will create a file right beside with an aditional extension suffix denoting the
                # state it is in.

    --key <file>   # Key (PEM) file to sign the document with (overrides config file).
    --cert <file>  # Cert (PEM) file to sign the document with (overrides config file).

    --all  # Signs all signodes in the document. Otherwise only the topmost will be signed.

    --xsd <file>  # XSD Schema definition file to check it against.

Commands:
    read  # Reads files and condenses them to lines delimited by newline. Useful to feed via stdin.

Notes:
    * There are currently no safeguards in place to avoid overwriting a file with nothing (emptying
      it) when something goes wrong and option --inplace is active. TODO.
"""
import os
import sys
import tempfile

import docopt
from lxml import etree

from sii.lib     import schemas, signature
from sii.lib     import exchange
from sii.lib     import validation as validate
from sii.lib     import types
from sii.lib.lib import xml

from .helpers import print_xml, read_xml, read_xmls, condense_xml, stack_extension, write_xml


def handle(config, args, argv):
    args = docopt.docopt(__doc__, argv=argv)

    if args['read']:
        handle_reading(args, config)
    elif args['bundle']:
        handle_bundling(args, config)
    elif args['unbundle']:
        handle_unbundling(args, config)
    elif args['gen']:
        handle_generate(args, config)
    elif args['sign']:
        handle_sign(args, config)
    elif args['verify']:
        handle_verify(args, config)
    elif args['void']:
        handle_void(args, config)
    else:
        raise RuntimeError("Conditional Fallthrough")


def handle_reading(args, config):
    for fname in args['<infile>']:
        with open(fname, 'rb') as fh:
            raw   = fh.read()
            clean = condense_xml(raw)

            try:
                sys.stdout.buffer.write(clean + b"\n")
                sys.stdout.buffer.flush()
            except:
                pass


def handle_bundling(args, config):
    if args['dte']:
        handle_bundling_dte(args, config)
    elif args['enviodte']:
        handle_bundling_enviodte(args, config)
    elif args['lv']:
        handle_bundling_lv(args, config)
    else:
        raise RuntimeError("Conditional Fallthrough")


def handle_bundling_dte(args, config):
    for xml_fpath in args['<infile>']:
        try:
            xml = read_xml(xml_fpath)
        except etree.XMLSyntaxError:
            print("Skipping invalid XML: {0}".format(xml_fpath), file=sys.stderr)
            continue

        caf_pool = types.CAFPool(config.static.cafs)
        dte      = schemas.bundle_dte(xml, caf_pool)

        if args['--inplace']:
            write_xml(dte, xml_fpath, encoding='ISO-8859-1')
        elif args['--suffixed']:
            write_xml(dte, stack_extension(xml_fpath, 'dte'), encoding='ISO-8859-1')
        else:
            print_xml(dte)


def handle_bundling_enviodte(args, config):
    dte_lst      = list(read_xmls(args['<infile>']))
    company_pool = types.CompanyPool.from_file(config.static.companies)

    to_sii = None
    if args['--sii']:
        to_sii = True
    elif args['--exchange']:
        to_sii = False

    assert to_sii is not None, "Must provide --sii or --exchange for enviodte bundling!"

    enviodte = schemas.bundle_enviodte(dte_lst, company_pool, to_sii=to_sii)

    if args['<outfile>']:
        write_xml(enviodte, args['<outfile>'], encoding='ISO-8859-1')
    else:
        print_xml(enviodte)


def handle_bundling_lv(args, config):
    dte_lst  = list(read_xmls(args['<infile>']))
    enviodte = schemas.bundle_libro_ventas(dte_lst)

    if args['<outfile>']:
        write_xml(enviodte, args['<outfile>'], encoding='ISO-8859-1')
    else:
        print_xml(enviodte)


def handle_unbundling(args, config):
    if args['enviodte']:
        handle_unbundling_enviodte(args, config)
    else:
        raise RuntimeError("Conditional Fallthrough")


def handle_unbundling_enviodte(args, config):
    for fname in args['<envio>']:
        enviodte = read_xml(fname)
        tree_lst = schemas.unbundle_enviodte(enviodte)

        if len(tree_lst) > 1 and args['--inplace']:
            raise SystemExit("<EnvioDTE> contains more than one <DTE>. Cannot unbundle '--inplace'.")

        for tree in tree_lst:
            if args['--generate']:
                dte = xml.wrap_xml(tree)

                dte_rut  = str(dte.Documento.Encabezado.Emisor.RUTEmisor).split('-')[0]
                dte_type = int(dte.Documento.Encabezado.IdDoc.TipoDTE)
                dte_id   = int(dte.Documento.Encabezado.IdDoc.Folio)

                ftempl  = "{company}_{type}_{id}.xml"
                ftarget = ftempl.format(company=dte_rut, type=dte_type, id=dte_id)

                write_xml(tree, ftarget, encoding='ISO-8859-1')
            elif args['--inplace']:
                write_xml(tree, fname, encoding='ISO-8859-1')
            else:
                print_xml(tree)


def handle_generate(args, config):
    xml = read_xml(args['<infile>'][0])

    reply_xml = None
    if args['doc']:
        if args['ack']:
            reply_xml = exchange.create_exchange_response(xml)  # Generate incoming ACK
        if args['ok']:
            reply_xml = exchange.create_document_approval(xml)  # Generate content OK
    if args['merch']:
        if args['ack']:
            reply_xml = exchange.create_merchandise_receipt(xml)  # Generate merchandise ACK-OK

    if reply_xml is None:
        raise RuntimeError("Conditional Fallthrough")
    else:
        write_xml(reply_xml, args['<outfile>'])


def handle_sign(args, config):
    infiles = []
    for path in args['<infile>']:
        if '.signed' not in path:
            infiles.append(path)
        else:
            print("Skipping: {0}".format(path), file=sys.stderr)

    for xml_fpath in infiles:
        try:
            doc_xml = read_xml(xml_fpath)
        except etree.XMLSyntaxError:
            print("Skipping invalid XML: {0}".format(xml_fpath), file=sys.stderr)
            continue

        key_path  = os.path.abspath(os.path.expanduser(config.auth.key))
        cert_path = os.path.abspath(os.path.expanduser(config.auth.cert))

        # Sign the <ds:Signature>
        sigfunc    = signature.sign_document_all if args['--all'] else signature.sign_document
        xml_signed = sigfunc(
            xml       = doc_xml,
            key_path  = key_path,   #  key_fh.name,
            cert_path = cert_path   #  cert_fh.name
        )

        if args['--inplace']:
            write_xml(xml_signed, xml_fpath, encoding='ISO-8859-1')
        elif args['--suffixed']:
            fpath = stack_extension(xml_fpath, 'signed')
            write_xml(xml_signed, fpath, encoding='ISO-8859-1')
        elif args['<outfile>']:
            write_xml(xml_signed, args['<outfile>'], encoding='ISO-8859-1')
        else:
            print_xml(xml_signed)


def handle_verify(args, config):
    if args['signature']:
        validate_signature(args, config)
    if args['schema']:
        validate_schema(args, config)


def validate_signature(args, config):
    for xml_fpath in args['<infile>']:
        xml = read_xml(xml_fpath)

        outcomes = {
            True:  "Good Signature.",
            False: "Bad Signature."
        }

        results = validate.validate_signatures(xml)
        for uri, validity in results:
            print("{0}: {1}: {2}".format(xml_fpath, uri, outcomes[validity]))


def validate_schema(args, config):
    xml_schema = None
    if args['--xsd']:
        with open(args['--xsd'], 'rb') as fh:
            xml_schema = etree.parse(fh)

    for xml_fpath in args['<infile>']:
        xml      = read_xml(xml_fpath)
        path_str = xml_fpath + ":"

        try:
            validate.validate_schema(xml, xml_schema)
        except etree.DocumentInvalid as exc:
            print(path_str, "Bad Schema. " + str(exc))
        else:
            print(path_str, "Good Schema.")


def handle_void(args, config):
    raise NotImplementedError("You need to have reliable info on available doc ids... thus implementation defered")
