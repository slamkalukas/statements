"""CAMT.053 parsing edge cases, incl. Tatra's embedded narrative fragments."""
from decimal import Decimal

from app.camt import parse_camt053

# Tatra puts a custom fragment in <AddtlNtryInf> as *escaped* text; the readable
# narrative is the <Nrtv> inside it.
ESCAPED = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document><BkToCstmrStmt><Stmt>
  <Ntry><Amt Ccy="EUR">12.50</Amt><CdtDbtInd>DBIT</CdtDbtInd>
    <BookgDt><Dt>2026-06-10</Dt></BookgDt>
    <AddtlNtryInf>&lt;NtryInf Ctg="Crd460" Ini="POS" MCC="5812" xmlns="urn:CurrentAccount:Statements:DataFile"&gt;&lt;Nrtv&gt;GP N\xc3\x81KUP POS&lt;/Nrtv&gt;&lt;/NtryInf&gt;</AddtlNtryInf>
  </Ntry>
</Stmt></BkToCstmrStmt></Document>"""

# A variant where <Nrtv> is a real nested element rather than escaped text.
NESTED = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document><BkToCstmrStmt><Stmt>
  <Ntry><Amt Ccy="EUR">9.90</Amt><CdtDbtInd>DBIT</CdtDbtInd>
    <BookgDt><Dt>2026-06-11</Dt></BookgDt>
    <AddtlNtryInf><NtryInf><Nrtv>PLATBA KARTOU</Nrtv></NtryInf></AddtlNtryInf>
  </Ntry>
</Stmt></BkToCstmrStmt></Document>"""


def test_escaped_ntryinf_extracts_narrative():
    rows = parse_camt053(ESCAPED)
    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("-12.50")
    assert rows[0]["description"] == "GP NÁKUP POS"  # not the raw <NtryInf> XML


def test_nested_nrtv_element_extracts_narrative():
    rows = parse_camt053(NESTED)
    assert rows[0]["description"] == "PLATBA KARTOU"
