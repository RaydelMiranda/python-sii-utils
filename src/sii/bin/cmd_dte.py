"""
Usage:
    sii dte [options] bundle dte       [--inplace | --suffixed] <infile>...
    sii dte [options] bundle enviodte  (--sii | --exchange) <outfile> <infile>...
    sii dte [options] bundle lv        <outfile> <infile>...
    sii dte [options] gen doc ack      <infile> <outfile>
    sii dte [options] gen doc ok       <infile> <outfile>
    sii dte [options] gen merch ack    <infile> <outfile>
    sii dte [options] sign             [--all] [--inplace | --suffixed | <outfile>] <infile>...
    sii dte [options] verify signature <infile>...
    sii dte [options] verify schema    [--xsd=<file>] <infile>...
    sii dte [options] void doc         <outfile> <infile>...

Options:
    --inplace   # Will modify the same file it read with the processed output.
    --suffixed  # Will create a file right beside with an aditional extension suffix denoting the
                # state it is in.

    --key <file>   # Key (PEM) file to sign the document with (overrides config file).
    --cert <file>  # Cert (PEM) file to sign the document with (overrides config file).

    --all  # Signs all signodes in the document. Otherwise only the topmost will be signed.

    --xsd <file>  # XSD Schema definition file to check it against.

Notes:
    * There are currently no safeguards in place to avoid overwriting a file with nothing (emptying
      it) when something goes wrong and option --inplace is active. TODO.
"""
import sys
import tempfile

import docopt
from lxml import etree

from sii.lib import schemas, signature
from sii.lib import exchange
from sii.lib import validation as validate

from .helpers import print_xml, read_xml, read_xmls, stack_extension, write_xml


def handle(config, args, argv):
    args = docopt.docopt(__doc__, argv=argv)
    config.update(args)

    if args['bundle']:
        handle_bundling(args, config)
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
    cns_engine = connect_cns_db(args, config)
    cns_sess   = session(cns_engine)

    for xml_fpath in args['<infile>']:
        try:
            xml = read_xml(xml_fpath)
        except etree.XMLSyntaxError:
            print("Skipping invalid XML: {0}".format(xml_fpath), file=sys.stderr)
            continue

        caf = cns.select_caf(xml, cns_sess)  # FIXME missing declaration swap with CAFPool from
        dte = schemas.bundle_dte(xml, caf)

        if args['--inplace']:
            write_xml(dte, xml_fpath, encoding='ISO-8859-1')
        elif args['--suffixed']:
            write_xml(dte, stack_extension(xml_fpath, 'dte'), encoding='ISO-8859-1')
        else:
            print_xml(dte)


def handle_bundling_enviodte(args, config):
    dte_lst  = list(read_xmls(args['<infile>']))

    to_sii = None
    if args['--sii']:
        to_sii = True
    elif args['--exchange']:
        to_sii = False

    assert to_sii is not None, "Must provide --sii or --exchange for enviodte bundling!"

    enviodte = schemas.bundle_enviodte(dte_lst, to_sii=to_sii)

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


def handle_generate(args, config):
    xml = read_xml(args['<infile>'][0])

    reply_xml = None
    if args['doc']:
        if args['ack']:  # Generate incoming ACK
            reply_xml = exchange.create_exchange_response(xml)
        if args['ok']:   # Generate content OK
            reply_xml = exchange.create_document_approval(xml)
    if args['merch']:
        if args['ack']:  # Generate merchandise ACK-OK
            reply_xml = exchange.create_merchandise_receipt(xml)

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

        # Load Sii key and certificate
        with open(config.key, 'rb') as fh:
            key_pem = fh.read()
        with open(config.cert, 'rb') as fh:
            cert_pem = fh.read()

        # Workaround, make xmlsec read from file
        key_fh  = tempfile.NamedTemporaryFile(mode='wb', buffering=0, delete=True)
        cert_fh = tempfile.NamedTemporaryFile(mode='wb', buffering=0, delete=True)
        key_fh.write(key_pem)
        cert_fh.write(cert_pem)

        # Sign the <ds:Signature>
        sigfunc    = signature.sign_document_all if args['--all'] else signature.sign_document
        xml_signed = sigfunc(
            xml       = doc_xml,
            key_path  = key_fh.name,
            cert_path = cert_fh.name
        )

        # Cleanup key and cert files
        key_fh.close()
        cert_fh.close()

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
