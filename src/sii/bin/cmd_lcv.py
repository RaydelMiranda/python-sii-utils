"""
Usage:
    sii lcv stats [options] <lcv> [--header --amounts --items]
    sii lcv edit  [options] <lcv> append <dte>
    sii lcv edit  [options] <lcv> remove <dte>
    sii lcv edit  [options] <lcv> remove <rut> <type> <id>
    sii lcv edit  [options] <lcv> merge <other>

Options:
    --stderr-header  # Output structural elements to stderr instead of stdout.
                     # Convenient for bypassing grep filtering!
"""
import sys
import collections

import docopt

from sii.lib.lib import xml
from sii.lib.lib import format as fmt

TAX_ADVANCE   = (19,)
TAX_RETENTION = (15, 33, 331, 34, 39)


def handle(config, args, argv):
    args = docopt.docopt(__doc__, argv=argv)

    if args['stats']:
        handle_stats(args, config)
    elif args['edit']:
        handle_edit(args, config)
    else:
        raise RuntimeError("Conditional Fallthrough")


def handle_stats(args, config):
    lcv = xml.read_xml(args['<lcv>'])

    assert lcv.__name__.endswith('LibroCompraVenta'), "Expected XML to be a <LibroCompraVenta/>!"

    stats = collections.OrderedDict()

    if args['--header']:
        stats['RUT Emisor'] = str(lcv.EnvioLibro.Caratula.RutEmisorLibro)
        stats['RUT Envia']  = str(lcv.EnvioLibro.Caratula.RutEnvia)
        stats['Tipo']       = str(lcv.EnvioLibro.Caratula.TipoOperacion)
        stats['Intervalo']  = str(lcv.EnvioLibro.Caratula.TipoLibro)
        stats['Tipo Envio'] = str(lcv.EnvioLibro.Caratula.TipoEnvio)
        stats['Periodo']    = str(lcv.EnvioLibro.Caratula.PeriodoTributario) + "\n"

    if args['--amounts']:
        for total in lcv.EnvioLibro.ResumenPeriodo.TotalesPeriodo:
            stat_type         = int(total.TpoDoc)
            stat_count        = int(total.TotDoc)
            stat_tax_exempt   = int(total.TotMntExe)
            stat_tax_vat      = int(total.TotMntIVA)
            stat_net          = int(total.TotMntNeto)
            stat_gross        = int(total.TotMntTotal)

            stat_tax_retained = 0
            stat_tax_advanced = 0
            tax_special = collections.defaultdict(lambda: 0)
            if total._has('TotOtrosImp'):
                for tax in total.TotOtrosImp:
                    code  = int(tax.CodImp)
                    value = int(tax.TotMntImp)

                    tax_special[code] += value

                    if code in TAX_RETENTION:
                        stat_tax_retained += value
                    elif code in TAX_ADVANCE:
                        stat_tax_advanced += value
                    else:
                        raise SystemExit("Missing Retention/Advance information for Tax code: {0}".format(code))

            lst_taxes_ret = []
            lst_taxes_adv = []
            for tax in sorted(tax_special.items(), key=lambda x: x[0]):
                code  = tax[0]
                value = tax[1]

                str_value = "{0}: {1}".format(code, _fmt_amount(value))

                if code in TAX_RETENTION:
                    lst_taxes_ret.append(str_value)
                elif code in TAX_ADVANCE:
                    lst_taxes_adv.append(str_value)
                else:
                    raise SystemExit("Missing Retention/Advance information for Tax code: {0}".format(code))
            str_taxes_ret = "({0})".format(", ".join(lst_taxes_ret)) if lst_taxes_ret else ""
            str_taxes_adv = "({0})".format(", ".join(lst_taxes_adv)) if lst_taxes_adv else ""

            type_stats                   = collections.OrderedDict()
            type_stats['Neto']           = _fmt_amount(stat_net,          '>', ' $', 10)
            type_stats['Exento']         = _fmt_amount(stat_tax_exempt,   '>', ' $', 10)
            type_stats['IVA']            = _fmt_amount(stat_tax_vat,      '>', ' $', 10)
            type_stats['IVA Retenido']   = _fmt_amount(stat_tax_retained, '>', ' $ {0}'.format(str_taxes_ret), 10)
            type_stats['IVA Anticipado'] = _fmt_amount(stat_tax_advanced, '>', ' $ {0}'.format(str_taxes_adv), 10)
            type_stats['Total']          = _fmt_amount(stat_gross,        '>', ' $', 10)

            type_stats_keyw = max([len(k) for k in type_stats.keys()])

            lst_body = ["{0:<{1}}: {2}".format(it[0], type_stats_keyw, it[1]) for it in type_stats.items()]
            str_body = "    " + "\n    ".join(lst_body)

            str_key   = "Totales [{0}] ({1})".format(stat_type, stat_count)
            str_stats = "\n{0}".format(str_body)

            stats[str_key] = str_stats + "\n"

    if stats:
        width = max([len(k) for k in stats.keys()])
        for key, value in stats.items():
            print("{0:<{1}}".format(key, width), ":", value)

    if args['--items']:
        items = list(lcv.EnvioLibro.Detalle)

        lst_rows = []
        lst_rows.append((  # header
            "Tpo",
            "Folio",
            "Fecha",
            "RUT",
            "Razon Social",
            "Neto",
            "Exento",
            "IVA",
            "Total",
            "IVA Ret",
            "IVA Ant"
        ))

        for item in sorted(list(lcv.EnvioLibro.Detalle), key=lambda row: int(row.TpoDoc)):
            str_type    = str(item.TpoDoc)
            str_id      = str(item.NroDoc)
            str_date    = str(item.FchDoc)
            str_rut     = fmt.rut(*str(item.RUTDoc).split('-'))
            str_name    = str(item.RznSoc)
            str_net     = _fmt_amount(int(item.MntNeto), '>', ' $')
            str_exempt  = _fmt_amount(int(item.MntExe),  '>', ' $')
            # str_vatrate = "{0}%".format(float(item.TasaImp))
            str_vat     = _fmt_amount(int(item.MntIVA),   '>', ' $')
            str_gross   = _fmt_amount(int(item.MntTotal), '>', ' $')

            stat_tax_ret = 0
            stat_tax_adv = 0
            if item._has('OtrosImp'):
                code   = int(item.OtrosImp.CodImp)
                rate   = float(item.OtrosImp.TasaImp)
                amount = int(item.OtrosImp.MntImp)

                if code in TAX_RETENTION:
                    stat_tax_ret += amount
                elif code in TAX_ADVANCE:
                    stat_tax_adv += amount
                else:
                    raise SystemExit("Missing Retention/Advance information for Tax code: {0}".format(code))

            str_tax_ret = _fmt_amount(stat_tax_ret, '>', ' $')
            str_tax_adv = _fmt_amount(stat_tax_adv, '>', ' $')

            lst_rows.append((
                str_type,
                str_id,
                str_date,
                str_rut,
                str_name,
                str_net,
                str_exempt,
                str_vat,
                str_gross,
                str_tax_ret,
                str_tax_adv
            ))

        widths = (
            max([len(row[0])  for row in lst_rows]),  # width_type
            max([len(row[1])  for row in lst_rows]),  # width_id
            max([len(row[2])  for row in lst_rows]),  # width_date
            max([len(row[3])  for row in lst_rows]),  # width_rut
            max([len(row[4])  for row in lst_rows]),  # width_name
            max([len(row[5])  for row in lst_rows]),  # width_net
            max([len(row[6])  for row in lst_rows]),  # width_exempt
            max([len(row[7])  for row in lst_rows]),  # width_vat
            max([len(row[8])  for row in lst_rows]),  # width_gross
            max([len(row[9])  for row in lst_rows]),  # width_tax_ret
            max([len(row[10]) for row in lst_rows])   # width_tax_adv
        )

        aligns_head = ('^', '^', '^', '^', '^', '^', '^', '^', '^', '^', '^')
        aligns_body = ('>', '>', '>', '>', '<', '>', '>', '>', '>', '>', '>')

        for idx, tup_row in enumerate(lst_rows):
            aligns  = aligns_head if idx == 0 else aligns_body
            str_row = "  ".join(["{0:{1}{2}}".format(col[0], col[1], col[2]) for col in zip(tup_row, aligns, widths)])

            if idx == 0:
                delim  = "-" * sum(widths)
                delim += "-" * (len(widths) - 1) * 2

                str_row += "\n" + delim

            if idx == 0 and args['--stderr-header']:
                print(str_row, file=sys.stderr)
            else:
                print(str_row)


def handle_edit(args, config):
    if args['append']:
        handle_edit_append(args, config)
    elif args['remove']:
        handle_edit_remove(args, config)
    elif args['merge']:
        handle_edit_merge(args, config)
    else:
        raise RuntimeError("Conditional Fallthrough")


def handle_edit_append(args, config):
    raise NotImplementedError("Pending implementation")


def handle_edit_remove(args, config):
    raise NotImplementedError("Pending implementation")


def handle_edit_merge(args, config):
    raise NotImplementedError("Pending implementation")


def _fmt_amount(amount, align=">", postfix="", width=0, alt_zero="-"):
    assert align in (">", "<"), "Alignment not supported: {0}".format(align)
    valstr = fmt.thousands(amount) if amount != 0 else alt_zero
    return "{0:{1}{2}}{3}".format(valstr, align, width, postfix)
