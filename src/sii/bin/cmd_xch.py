""" Exchange Documents with other Emitters

Usage:
    sii xch [options] email --from <address> (--to <address> | --to-csv <csv> | --to-ws) [--bcc <>]
                            [--preamble <path> | --message <msg>]
                            [--batch]
                            <enviodte>...

Options:
    # SMTP Information and Options
    --mail-host <host>      # Host
    --mail-user <user>      # User
    --mail-passwd <passwd>  # Password
    --mail-port <port>      # Port [default: 587]
    --mail-no-tls           # Deactivate TLS (no STARTTLS handshake will occur)

    # Email Addressing
    --from <address>  # Specify emitter address.

    --to <address>    # Specify receiver directly.
    --to-csv <csv>    # Resolve from SII provided CSV list (see Notes).
    --to-ws           # Resolve by querying SII ws/web.

    --bcc <bcc>       # Add a BCC copy recipient.

    # Email Content
    --preamble <path>  # Message from a path to a file with it.
    --message <msg>    # Message directly from args.

    # Application Control
    --batch  # Skip file on failure to lookup recipient. Useful when some recipients are no electronic contributors,
             # works with --to-csv and --to-ws.

Notes:
    * SII provides a list of all contributors/emitters, including their exchange email addresses
      at https://palena.sii.cl/cvc_cgi/dte/ce_empresas_dwnld (cert auth required).

      The CSV headers are as follows:
        RUT; RAZON SOCIAL; NUMERO RESOLUCION; FECHA RESOLUCION; MAIL INTERCAMBIO; URL
      Separator as can be seen is ';', no string quotes.
"""
import os
import sys
import csv
import smtplib
import collections

from email.mime.text      import MIMEText
from email.mime.multipart import MIMEMultipart

import docopt

from lxml import etree

from sii.lib     import validation as valid
from sii.lib.lib import xml, output

_CSV_CACHE = {}
_CSV_ROW   = collections.namedtuple('CsvRow', ['rut', 'rznsoc', 'url', 'mail', 'res', 'fchres'])

pth_expand = lambda pth: os.path.abspath(os.path.expanduser(pth))


def handle(config, argv):
    args = docopt.docopt(__doc__, argv=argv)

    if args['email']:
        handle_email(args, config)
    else:
        raise RuntimeError("Conditional Fallthrough")


def handle_email(args, config):
    mail_user   = args['--mail-user']
    mail_passwd = args['--mail-passwd']
    mail_host   = args['--mail-host']
    mail_port   = int(args['--mail-port'])
    mail_tls    = not args['--mail-no-tls']

    sendr_addr = args['--from']
    recpt_bcc  = args['--bcc'] if args['--bcc'] else None

    for fp in args['<enviodte>']:
        assert os.path.isfile(fp), "Could not find specified file: {0}".format(fp)

        recpt_rut  = None
        recpt_addr = None

        # load xml
        enviodte = xml.read_xml(fp)
        tree     = xml.dump_etree(enviodte)

        # validate schema
        valid.validate_schema(tree)

        # extract recipient information
        assert enviodte.__name__.endswith('EnvioDTE'), "Currently only <EnvioDTE> XML's supported!"
        recpt_rut = str(enviodte.SetDTE.Caratula.RutReceptor)

        # resolve recipient email
        if args['--to']:
            recpt_addr = args['--to']
        elif args['--to-csv']:
            try:
                recpt      = _resolve_csv(recpt_rut, pth_expand(args['--to-csv']))
                recpt_addr = recpt.mail
            except AssertionError as exc:
                if args['--batch']:
                    print(output.cyan("SKIPPED") + " {0} - {1}".format(fp, str(exc)), file=sys.stderr)
                    continue
                else:
                    raise
        elif args['--to-ws']:
            raise SystemExit("Querying WS for receiver email is not supported ...yet")
        else:
            raise RuntimeError("Conditional Fallthrough")

        # read message header/body to go before attachment
        message = None

        if args['--preamble']:
            fpath = pth_expand(args['--preamble'])

            if not os.path.isfile(fpath):
                raise SystemExit("Could not read message from provided file: '{0}'".format(fpath))

            with open(fpath, 'r') as fh:
                message = fh.read()

        if args['--message']:
            message = args['--message']

        # build email
        msg = _create_mail(
            sender    = sendr_addr,
            recipient = recpt_addr,
            bcc       = recpt_bcc,
            subject   = _build_subject(enviodte),
            message   = message
        )

        _attach_xml(msg=msg, enviodte=enviodte)
        _send_mail(msg=msg, user=mail_user, passwd=mail_passwd, host=mail_host, port=mail_port, tls=mail_tls)

        out_bcc = "Bcc: {0}".format(recpt_bcc) if recpt_bcc else ""
        print(output.green("SENT   ") + " {0} - From: {1} To: {2} {3}".format(fp, sendr_addr, recpt_addr, out_bcc), file=sys.stderr)


def _resolve_csv(rut, csv_path):
    rut = rut.upper()

    global _CSV_CACHE
    db = _CSV_CACHE.get(csv_path, None)

    if not db:
        db = {}

        with open(csv_path, 'r', encoding='ISO-8859-1') as fh:
            reader  = csv.reader(fh, delimiter=';')
            headers = next(reader)

            assert 'NUMERO RESOLUCION' in headers, "Expected 'NUMERO RESOLUCION' in provided csv!"
            assert 'RAZON SOCIAL'      in headers, "Expected 'RAZON SOCIAL' in provided csv!"
            assert 'URL'               in headers, "Expected 'URL' in provided csv!"
            assert 'MAIL INTERCAMBIO'  in headers, "Expected 'MAIL INTERCAMBIO' in provided csv!"
            assert 'FECHA RESOLUCION'  in headers, "Expected 'FECHA RESOLUCION' in provided csv!"
            assert 'RUT'               in headers, "Expected 'RUT' in provided csv!"

            for row in reader:
                db[row[0].upper()] = _CSV_ROW(
                    rut    = row[0].upper(),
                    rznsoc = row[1],
                    url    = row[5],
                    mail   = row[4],
                    res    = row[2],
                    fchres = row[3]
                )

        _CSV_CACHE[csv_path] = db

    email = db.get(rut, None)
    assert email, "Could not find: ({0}). Is he a electronic emitter/receiver?".format(rut)
    return email


def _create_mail(sender, recipient, bcc, subject, message):
    msg = MIMEMultipart()

    msg['From']    = sender
    msg['To']      = recipient
    if bcc:
        msg['BCC'] = bcc
    msg['Subject'] = subject

    if message:
        text = MIMEText(message, _charset="UTF-8")
        msg.attach(text)

    return msg


def _attach_xml(msg, enviodte):
    assert isinstance(msg, MIMEMultipart), "Programming Error!"
    assert isinstance(enviodte, xml.XML),  "Programming Error!"

    pthname = _build_pathname(enviodte)
    payload = xml.dump_xml(enviodte, pretty_print=True, encoding='ISO-8859-1', xml_declaration=True)

    txt = MIMEText(payload, "xml", "ISO-8859-1")
    txt['Content-Disposition'] = 'attachment; filename="{0}"'.format(pthname)

    msg.attach(txt)


def _send_mail(msg, user, passwd, host, port=587, tls=True):
    assert isinstance(msg, MIMEMultipart), "Programming Error!"

    server = smtplib.SMTP()
    server.connect(host=host, port=port)

    if tls:
        server.starttls()

    server.login(user=user, password=passwd)
    server.send_message(msg)


def _build_subject(enviodte):
    dte_rut    = str(enviodte.SetDTE.DTE.Documento.Encabezado.Emisor.RUTEmisor).split('-')[0]
    dte_type   = int(enviodte.SetDTE.DTE.Documento.Encabezado.IdDoc.TipoDTE)
    dte_serial = int(enviodte.SetDTE.DTE.Documento.Encabezado.IdDoc.Folio)

    return "EnvioDTE {0}-{1}-{2}".format(dte_rut, dte_type, dte_serial)


def _build_pathname(enviodte):
    dte_rut    = str(enviodte.SetDTE.DTE.Documento.Encabezado.Emisor.RUTEmisor).split('-')[0]
    dte_type   = int(enviodte.SetDTE.DTE.Documento.Encabezado.IdDoc.TipoDTE)
    dte_serial = int(enviodte.SetDTE.DTE.Documento.Encabezado.IdDoc.Folio)

    return "{0}_{1}_{2}.xml".format(dte_rut, dte_type, dte_serial)


# def _extract_dte(enviodte):
#     if enviodte.__name__.endswith('DTE'):
#         return enviodte

#     if enviodte.__name__.endswith('SetDTE'):
#         return enviodte.DTE

#     if enviodte.__name__.endswith('EnvioDTE'):
#         return enviodte.SetDTE.DTE

#     raise SystemExit(
#         "Could not unpack <DTE> from given XML!"
#     )
