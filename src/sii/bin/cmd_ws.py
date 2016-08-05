""" Interact with Sii Servers (Upload, verify states, ...)

Usage:
    sii ws test connect [--maullin] [--palena] [--key=<key>] [--cert=<cert>]
    sii ws upload       (--maullin | --palena) [--dry-run] [--disable-ssl-verify] <infile>

Options:
    --maullin  # Act on the SII official testing server.
    --palena   # Act on the SII official production server.

    --disable-ssl-verify  # Disables the SSL cert validity check.
"""
import os
import sys

from sii.lib import upload

from docopt import docopt
from lxml   import etree

fullpath = lambda pth: os.path.abspath(os.path.expanduser(pth))


def handle(config, args, argv):
    args = docopt(__doc__, argv=argv)

    if args['test']:
        handle_test(args, config)
    elif args['upload']:
        handle_upload(args, config)
    else:
        raise RuntimeError("Conditional Fallthrough.")


def handle_test(args, config):
    if args['connect']:
        key_pth  = fullpath(config.auth.key)
        cert_pth = fullpath(config.auth.cert)

        if args['--maullin']:
            ret = upload.test_connection(key_pth, cert_pth, upload.HOST_TESTING)

            if ret is True:
                status = "Successful"
            else:
                status = "Failed with status: {0}".format(ret)

            print("Connection to Maullin:", status, file=sys.stderr)

        if args['--palena']:
            ret = upload.test_connection(key_pth, cert_pth, upload.HOST_PRODUCTION)

            if ret is True:
                status = "Successful"
            else:
                status = "Failed with status: {0}".format(ret)

            print("Connection to Palena:", status, file=sys.stderr)

        return


def handle_upload(args, config):
    server = None

    # Determine server
    if args['--maullin']:
        server = upload.HOST_TESTING
    elif args['--palena']:
        server = upload.HOST_PRODUCTION
    else:
        raise ValueError("Could not determine target server to upload to")

    with open(args['<infile>'], 'rb') as fh:
        xml  = etree.parse(fh)
        root = xml.getroot()

        sii_id = upload.upload_document(
            document = root,
            key_pth  = fullpath(config.auth.key),
            cert_pth = fullpath(config.auth.cert),
            server   = server,
            dryrun   = args['--dry-run'],
            verify   = not args['--disable-ssl-verify']
        )

        print("Upload Number: {0}".format(sii_id))
