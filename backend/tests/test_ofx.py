"""OFX 2.x (XML) parsing — e.g. Tatra Banka credit-card exports."""
from decimal import Decimal

from app.ofx import parse_ofx
from app.statements import parse_statement

OFX_CARD = b"""<?xml version='1.0' encoding='UTF-8'?>
<?OFX OFXHEADER='200' VERSION='211' SECURITY='NONE'?>
<OFX xmlns="http://ofx.net/types/2003/04" xmlns:TB="http://moja.tatrabanka.sk/xmlns/card.1.1">
  <CREDITCARDMSGSRSV1><CCSTMTTRNRS><CCSTMTRS><BANKTRANLIST>
    <STMTTRN>
      <TRNTYPE>DEBIT</TRNTYPE><DTPOSTED>20260521</DTPOSTED>
      <TRNAMT>21.40</TRNAMT><CURRENCY>EUR</CURRENCY>
      <NAME>WWW.WEBSUPPORT.SK COMFO</NAME>
    </STMTTRN>
    <STMTTRN>
      <TRNTYPE>DEBIT</TRNTYPE><DTPOSTED>20260518</DTPOSTED>
      <TRNAMT>16.17</TRNAMT><CURRENCY>EUR</CURRENCY>
      <NAME>alza.sk</NAME>
    </STMTTRN>
    <STMTTRN>
      <TRNTYPE>CREDIT</TRNTYPE><DTPOSTED>20260510</DTPOSTED>
      <TRNAMT>50.00</TRNAMT><CURRENCY>EUR</CURRENCY>
      <NAME>Refund</NAME>
    </STMTTRN>
  </BANKTRANLIST></CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1>
</OFX>"""


def test_parse_ofx_signs_and_fields():
    rows = parse_ofx(OFX_CARD)
    assert len(rows) == 3
    websupport = rows[0]
    assert websupport["txn_date"].isoformat() == "2026-05-21"
    assert websupport["amount"] == Decimal("-21.40")  # DEBIT -> money out
    assert websupport["description"] == "WWW.WEBSUPPORT.SK COMFO"
    assert websupport["currency"] == "EUR"
    # CREDIT stays positive (incoming / refund).
    assert rows[2]["amount"] == Decimal("50.00")


def test_dispatcher_detects_ofx_over_camt():
    rows, fmt = parse_statement(OFX_CARD)
    assert fmt == "OFX"
    assert len(rows) == 3
    # Two outgoing card purchases (the refund is incoming).
    assert sum(1 for r in rows if r["amount"] < 0) == 2
