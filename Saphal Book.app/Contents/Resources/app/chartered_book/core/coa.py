"""
Standard chart of accounts for a Nepali business.

The grouping follows the presentation used in NFRS and NAS financial
statements, which is what an audit in Nepal expects to see: a Statement of
Financial Position split into non current and current, and a Statement of
Profit or Loss running from revenue down through cost of sales, employee
benefit expense, other operating expense, finance cost, depreciation and tax.

Every ledger is marked for the kind of business it suits:

    both      created for every company
    trading   created for a company that buys and sells goods
    service   created for a professional practice

A company created as "both" receives everything. Nothing here is locked. Any
account can be renamed, deactivated or added to once the books are open, and
accounts marked as system are the ones the software posts to automatically, so
those cannot be deleted.
"""

# code, name, nepali name, parent code, nature, statement, section, sort
GROUPS = [
    # Assets
    ("1000", "Assets", "सम्पत्ति", None, "asset", "BS", "assets", 100),
    ("1100", "Non Current Assets", "गैर चालु सम्पत्ति", "1000", "asset", "BS", "assets", 110),
    ("1110", "Property, Plant and Equipment", "", "1100", "asset", "BS", "assets", 111),
    ("1130", "Capital Work in Progress", "", "1100", "asset", "BS", "assets", 113),
    ("1140", "Intangible Assets", "", "1100", "asset", "BS", "assets", 114),
    ("1150", "Long Term Investments", "", "1100", "asset", "BS", "assets", 115),
    ("1160", "Deferred Tax Asset", "", "1100", "asset", "BS", "assets", 116),
    ("1170", "Long Term Loans, Advances and Deposits", "", "1100", "asset", "BS", "assets", 117),
    ("1180", "Investment Property", "", "1100", "asset", "BS", "assets", 118),
    ("1190", "Right of Use Assets", "", "1100", "asset", "BS", "assets", 119),

    ("1200", "Current Assets", "चालु सम्पत्ति", "1000", "asset", "BS", "assets", 120),
    ("1210", "Inventories", "मौज्दात", "1200", "asset", "BS", "assets", 121),
    ("1220", "Trade Receivables", "व्यापारिक प्राप्य", "1200", "asset", "BS", "assets", 122),
    ("1230", "Advances, Prepayments and Deposits", "पेश्की, अग्रिम भुक्तानी र धरौटी", "1200", "asset", "BS", "assets", 123),
    ("1240", "Tax Assets", "कर सम्पत्ति", "1200", "asset", "BS", "assets", 124),
    ("1250", "Cash in Hand", "नगद मौज्दात", "1200", "asset", "BS", "assets", 125),
    ("1260", "Bank Balances", "बैंक मौज्दात", "1200", "asset", "BS", "assets", 126),
    ("1270", "Short Term Investments", "अल्पकालीन लगानी", "1200", "asset", "BS", "assets", 127),
    ("1280", "Other Current Assets", "अन्य चालु सम्पत्ति", "1200", "asset", "BS", "assets", 128),

    # Liabilities
    ("2000", "Liabilities", "दायित्व", None, "liability", "BS", "liabilities", 200),
    ("2100", "Non Current Liabilities", "गैर चालु दायित्व", "2000", "liability", "BS", "liabilities", 210),
    ("2110", "Long Term Borrowings", "दीर्घकालीन ऋण", "2100", "liability", "BS", "liabilities", 211),
    ("2120", "Deferred Tax Liability", "स्थगित कर दायित्व", "2100", "liability", "BS", "liabilities", 212),
    ("2130", "Long Term Provisions", "", "2100", "liability", "BS", "liabilities", 213),
    ("2140", "Lease Liabilities", "", "2100", "liability", "BS", "liabilities", 214),

    ("2200", "Current Liabilities", "चालु दायित्व", "2000", "liability", "BS", "liabilities", 220),
    ("2210", "Trade Payables", "व्यापारिक भुक्तानी दिनुपर्ने", "2200", "liability", "BS", "liabilities", 221),
    ("2220", "Short Term Borrowings", "अल्पकालीन ऋण", "2200", "liability", "BS", "liabilities", 222),
    ("2230", "Advance from Customers", "ग्राहकबाट पेश्की", "2200", "liability", "BS", "liabilities", 223),
    ("2240", "Value Added Tax and Duties", "मूल्य अभिवृद्धि कर तथा महसुल", "2200", "liability", "BS", "liabilities", 224),
    ("2250", "Tax Deducted at Source", "स्रोतमा कट्टी कर", "2200", "liability", "BS", "liabilities", 225),
    ("2260", "Employee Related Payables", "कर्मचारी सम्बन्धी दायित्व", "2200", "liability", "BS", "liabilities", 226),
    ("2270", "Accrued and Outstanding Expenses", "भुक्तानी बाँकी खर्च", "2200", "liability", "BS", "liabilities", 227),
    ("2280", "Short Term Provisions", "अल्पकालीन व्यवस्था", "2200", "liability", "BS", "liabilities", 228),
    ("2290", "Other Current Liabilities", "अन्य चालु दायित्व", "2200", "liability", "BS", "liabilities", 229),

    # Equity
    ("3000", "Equity", "इक्विटी", None, "equity", "BS", "equity", 300),
    ("3100", "Capital", "पुँजी", "3000", "equity", "BS", "equity", 310),
    ("3200", "Reserves and Surplus", "जगेडा तथा बचत", "3000", "equity", "BS", "equity", 320),
    ("3300", "Drawings", "निकासी", "3000", "equity", "BS", "equity", 330),

    # Income
    ("4000", "Income", "आय", None, "income", "PL", "income", 400),
    ("4100", "Revenue from Operations", "कारोबारबाट आम्दानी", "4000", "income", "PL", "revenue", 410),
    ("4110", "Sale of Goods", "सामान बिक्री", "4100", "income", "PL", "revenue", 411),
    ("4120", "Service Income", "सेवा आम्दानी", "4100", "income", "PL", "revenue", 412),
    ("4130", "Sales Returns and Discounts", "बिक्री फिर्ता र छुट", "4100", "income", "PL", "revenue", 413),
    ("4200", "Other Income", "", "4000", "income", "PL", "other_income", 420),
    ("4300", "Other Comprehensive Income", "", None, "income", "PL", "oci", 430),

    # Cost of sales
    ("5000", "Cost of Sales", "बिक्री लागत", None, "expense", "PL", "cost_of_sales", 500),
    ("5100", "Purchases", "खरिद", "5000", "expense", "PL", "cost_of_sales", 510),
    ("5200", "Direct Expenses", "प्रत्यक्ष खर्च", "5000", "expense", "PL", "cost_of_sales", 520),
    ("5300", "Stock Movement", "मौज्दात परिवर्तन", "5000", "expense", "PL", "cost_of_sales", 530),
    # Where the books are kept on the perpetual system, the cost of what was
    # sold is charged here as each sale is made, rather than being arrived at
    # once a year by opening stock plus purchases less closing stock.
    ("5400", "Cost of Goods Sold", "बेचिएको सामानको लागत", "5000", "expense", "PL",
     "cost_of_sales", 540),

    # Operating expenses
    ("6000", "Operating Expenses", "सञ्चालन खर्च", None, "expense", "PL", "operating", 600),
    ("6100", "Employee Benefit Expenses", "कर्मचारी सुविधा खर्च", "6000", "expense", "PL", "employee", 610),
    ("6200", "Administrative Expenses", "प्रशासनिक खर्च", "6000", "expense", "PL", "administrative", 620),
    ("6300", "Selling and Distribution Expenses", "बिक्री तथा वितरण खर्च", "6000", "expense", "PL", "selling", 630),

    # Finance, depreciation and other
    ("7000", "Finance Cost and Other Expenses", "वित्तीय तथा अन्य खर्च", None, "expense", "PL", "other_expense", 700),
    ("7100", "Finance Costs", "वित्तीय खर्च", "7000", "expense", "PL", "finance", 710),
    ("7200", "Depreciation and Amortisation", "ह्रास तथा परिशोधन", "7000", "expense", "PL", "depreciation", 720),
    ("7300", "Other Expenses", "अन्य खर्च", "7000", "expense", "PL", "other_expense", 730),

    # Tax
    ("8000", "Tax Expense", "कर खर्च", None, "expense", "PL", "tax", 800),
    ("8100", "Income Tax Expense", "आयकर खर्च", "8000", "expense", "PL", "tax", 810),
]


# code, name, nepali name, group code, kind, applies, options
# kind drives behaviour: cash, bank and stock accounts get special screens,
# vat_output / vat_input are posted by the VAT engine, and so on.
LEDGERS = [
    # Property, plant and equipment
    ("1111", "Land", "जग्गा", "1110", "fixed_asset", "both", {}),
    ("1112", "Building", "भवन", "1110", "fixed_asset", "both", {}),
    ("1113", "Leasehold Improvements", "भाडाको सम्पत्तिमा सुधार", "1110", "fixed_asset", "both", {}),
    ("1114", "Plant and Machinery", "प्लान्ट तथा मेसिनरी", "1110", "fixed_asset", "trading", {}),
    ("1115", "Furniture and Fixtures", "फर्निचर तथा फिक्स्चर", "1110", "fixed_asset", "both", {}),
    ("1116", "Office Equipment", "कार्यालय उपकरण", "1110", "fixed_asset", "both", {}),
    ("1117", "Computer and Accessories", "कम्प्युटर तथा सहायक सामग्री", "1110", "fixed_asset", "both", {}),
    ("1118", "Vehicles", "सवारी साधन", "1110", "fixed_asset", "both", {}),
    ("1119", "Tools and Equipment", "औजार तथा उपकरण", "1110", "fixed_asset", "trading", {}),

    # Accumulated depreciation sits in the same group as the cost it relates to,
    # so the group totals to the carrying amount. That is what belongs on the
    # face of the statement under NAS 01, with cost and depreciation shown
    # separately in the note behind it.
    ("1121", "Accumulated Depreciation on Building", "", "1110", "contra_asset", "both", {}),
    ("1122", "Accumulated Depreciation on Plant and Machinery", "", "1110", "contra_asset", "trading", {}),
    ("1123", "Accumulated Depreciation on Furniture and Fixtures", "", "1110", "contra_asset", "both", {}),
    ("1124", "Accumulated Depreciation on Office Equipment", "", "1110", "contra_asset", "both", {}),
    ("1125", "Accumulated Depreciation on Computer", "", "1110", "contra_asset", "both", {}),
    ("1126", "Accumulated Depreciation on Vehicles", "", "1110", "contra_asset", "both", {}),
    ("1127", "Accumulated Depreciation on Leasehold Improvements", "", "1110", "contra_asset", "both", {}),
    ("1128", "Accumulated Depreciation on Tools and Equipment", "", "1110", "contra_asset", "trading", {}),

    ("1131", "Capital Work in Progress", "निर्माणाधीन पुँजीगत कार्य", "1130", "general", "both", {}),
    ("1141", "Computer Software", "कम्प्युटर सफ्टवेयर", "1140", "fixed_asset", "both", {}),
    ("1142", "Goodwill", "ख्याति", "1140", "fixed_asset", "both", {}),
    ("1143", "Trademark and Licences", "ट्रेडमार्क तथा इजाजतपत्र", "1140", "fixed_asset", "both", {}),
    ("1144", "Accumulated Amortisation", "संचित परिशोधन", "1140", "contra_asset", "both", {}),

    ("1151", "Investment in Shares", "शेयरमा लगानी", "1150", "general", "both", {}),
    ("1152", "Investment in Subsidiaries and Associates", "", "1150", "general", "both", {}),
    ("1153", "Fixed Deposit, Long Term", "दीर्घकालीन मुद्दती निक्षेप", "1150", "general", "both", {}),
    ("1161", "Deferred Tax Asset", "स्थगित कर सम्पत्ति", "1160", "general", "both", {}),

    ("1171", "Security Deposit", "धरौटी", "1170", "general", "both", {}),
    ("1172", "Rent Deposit", "भाडा धरौटी", "1170", "general", "both", {}),
    ("1173", "Utility Deposit", "सेवा शुल्क धरौटी", "1170", "general", "both", {}),
    ("1174", "Loan to Related Party", "", "1170", "general", "both", {}),
    ("1181", "Investment Property, at Cost", "", "1180", "fixed_asset", "both",
     {"notes": "Land or buildings held to earn rent or for capital appreciation, "
               "measured under NAS 40."}),
    ("1182", "Accumulated Depreciation on Investment Property", "", "1180", "contra_asset", "both", {}),
    ("1191", "Right of Use Asset", "", "1190", "fixed_asset", "both",
     {"notes": "Recognised where a lease is capitalised under NFRS 16. Not required "
               "for an entity reporting under NFRS for SMEs."}),
    ("1192", "Accumulated Depreciation on Right of Use Asset", "", "1190", "contra_asset", "both", {}),

    # Inventories
    ("1211", "Stock in Trade", "व्यापारिक मौज्दात", "1210", "stock", "trading",
     {"is_system": 1, "notes": "Closing stock of goods held for resale. Posted by the stock engine."}),
    ("1212", "Goods in Transit", "बाटोमा रहेको सामान", "1210", "general", "trading", {}),
    ("1213", "Consumables and Spares", "उपभोग्य वस्तु तथा पार्टपुर्जा", "1210", "general", "trading", {}),
    ("1214", "Packing Material", "प्याकिङ सामग्री", "1210", "general", "trading", {}),
    ("1215", "Work in Progress, Services", "सेवा कार्य प्रगति", "1210", "general", "service",
     {"notes": "Unbilled time and cost on assignments in hand."}),

    # Receivables
    ("1221", "Sundry Debtors", "विविध ऋणी", "1220", "party_customer", "both",
     {"is_system": 1, "notes": "Control account. Each customer gets its own ledger under this group."}),
    ("1222", "Bills Receivable", "प्राप्य बिल", "1220", "general", "both", {}),
    ("1223", "Unbilled Revenue", "बिल नगरिएको आम्दानी", "1220", "general", "service", {}),
    ("1224", "Provision for Doubtful Debts", "शंकास्पद ऋणको व्यवस्था", "1220", "contra_asset", "both", {}),

    # Advances and prepayments
    ("1231", "Advance to Suppliers", "आपूर्तिकर्तालाई पेश्की", "1230", "general", "both", {}),
    ("1232", "Staff Advance", "कर्मचारी पेश्की", "1230", "general", "both", {}),
    ("1233", "Prepaid Rent", "अग्रिम भाडा", "1230", "general", "both", {}),
    ("1234", "Prepaid Insurance", "अग्रिम बीमा", "1230", "general", "both", {}),
    ("1235", "Prepaid Expenses", "अग्रिम खर्च", "1230", "general", "both", {}),
    ("1236", "Accrued Income", "प्राप्त हुन बाँकी आम्दानी", "1230", "general", "both", {}),

    # Tax assets
    ("1241", "VAT Input Credit", "मूल्य अभिवृद्धि कर क्रेडिट", "1240", "vat_input", "both",
     {"is_system": 1, "vat_rate_bp": 1300,
      "notes": "Purchase VAT recoverable under the Value Added Tax Act, 2052."}),
    ("1242", "VAT Credit Carried Forward", "जगेडा मूल्य अभिवृद्धि कर", "1240", "general", "both", {}),
    ("1243", "Advance Income Tax", "अग्रिम आयकर", "1240", "general", "both", {}),
    ("1244", "TDS Receivable", "कट्टी भएको अग्रिम कर", "1240", "general", "both",
     {"notes": "Tax deducted at source by customers, claimable against the annual assessment."}),
    ("1245", "Excise Duty Receivable", "अन्तःशुल्क प्राप्य", "1240", "general", "trading", {}),

    # Cash and bank
    ("1251", "Cash in Hand", "नगद मौज्दात", "1250", "cash", "both", {"is_system": 1}),
    ("1252", "Petty Cash", "फुटकर नगद", "1250", "cash", "both", {}),
    ("1261", "Bank Account, Current", "बैंक खाता, चल्ती", "1260", "bank", "both", {"reconcilable": 1}),
    ("1262", "Bank Account, Savings", "बैंक खाता, बचत", "1260", "bank", "both", {"reconcilable": 1}),
    ("1263", "Cheques in Hand", "हातमा रहेको चेक", "1260", "general", "both", {}),
    ("1271", "Fixed Deposit, Short Term", "अल्पकालीन मुद्दती निक्षेप", "1270", "general", "both", {}),
    ("1281", "Suspense Account", "स्थगित खाता", "1280", "general", "both",
     {"notes": "Temporary holding only. Must be cleared before the books are closed."}),

    # Non current liabilities
    ("2111", "Term Loan from Bank", "बैंकबाट अवधि कर्जा", "2110", "general", "both", {}),
    ("2112", "Vehicle Loan", "सवारी कर्जा", "2110", "general", "both", {}),
    ("2113", "Loan from Directors and Partners", "सञ्चालक तथा साझेदारबाट कर्जा", "2110", "general", "both", {}),
    ("2114", "Loan from Related Party", "सम्बन्धित पक्षबाट कर्जा", "2110", "general", "both", {}),
    ("2121", "Deferred Tax Liability", "स्थगित कर दायित्व", "2120", "general", "both", {}),
    ("2131", "Provision for Gratuity", "उपदान व्यवस्था", "2130", "general", "both", {}),
    ("2132", "Provision for Leave Encashment", "", "2130", "general", "both", {}),
    ("2141", "Lease Liability, Non Current", "", "2140", "general", "both", {}),

    # Payables
    ("2211", "Sundry Creditors", "विविध साहु", "2210", "party_supplier", "both",
     {"is_system": 1, "notes": "Control account. Each supplier gets its own ledger under this group."}),
    ("2212", "Bills Payable", "भुक्तानी दिनुपर्ने बिल", "2210", "general", "both", {}),
    ("2213", "Creditors for Expenses", "खर्चको साहु", "2210", "general", "both", {}),
    ("2214", "Creditors for Capital Goods", "पुँजीगत सामानको साहु", "2210", "general", "both", {}),

    ("2221", "Bank Overdraft", "बैंक ओभरड्राफ्ट", "2220", "bank", "both", {"reconcilable": 1}),
    ("2222", "Cash Credit Loan", "नगद कर्जा", "2220", "bank", "both", {"reconcilable": 1}),
    ("2223", "Short Term Loan", "अल्पकालीन कर्जा", "2220", "general", "both", {}),
    ("2231", "Advance from Customers", "ग्राहकबाट पेश्की", "2230", "general", "both", {}),

    # Value added tax and duties
    ("2241", "VAT Output Payable", "मूल्य अभिवृद्धि कर भुक्तानी", "2240", "vat_output", "both",
     {"is_system": 1, "vat_rate_bp": 1300,
      "notes": "Sales VAT collected under the Value Added Tax Act, 2052."}),
    ("2242", "VAT Payable, Net", "खुद मूल्य अभिवृद्धि कर", "2240", "general", "both",
     {"notes": "Net position after setting input credit against output tax for the month."}),
    ("2243", "Excise Duty Payable", "अन्तःशुल्क भुक्तानी", "2240", "general", "trading", {}),
    ("2244", "Health Service Tax Payable", "स्वास्थ्य सेवा कर", "2240", "general", "both", {}),
    ("2245", "Education Service Fee Payable", "शिक्षा सेवा शुल्क", "2240", "general", "both", {}),
    ("2246", "Local Tax Payable", "स्थानीय कर", "2240", "general", "both", {}),
    ("2247", "Income Tax Payable", "आयकर भुक्तानी", "2240", "general", "both", {}),

    # Tax deducted at source
    ("2251", "TDS Payable on Salary", "तलबमा कट्टी कर", "2250", "tds", "both", {"tds_section": "87"}),
    ("2252", "TDS Payable on Rent", "भाडामा कट्टी कर", "2250", "tds", "both",
     {"tds_section": "88-rent", "tds_rate_bp": 1000}),
    ("2253", "TDS Payable on Service Fee", "सेवा शुल्कमा कट्टी कर", "2250", "tds", "both",
     {"tds_section": "88-svc", "tds_rate_bp": 1500}),
    ("2254", "TDS Payable on Contract Payment", "ठेक्का भुक्तानीमा कट्टी कर", "2250", "tds", "both",
     {"tds_section": "89-contract", "tds_rate_bp": 150}),
    ("2255", "TDS Payable on Commission", "कमिशनमा कट्टी कर", "2250", "tds", "both",
     {"tds_section": "88-comm", "tds_rate_bp": 1500}),
    ("2256", "TDS Payable on Interest", "ब्याजमा कट्टी कर", "2250", "tds", "both",
     {"tds_section": "88-int-o", "tds_rate_bp": 1500}),
    ("2257", "TDS Payable, Other", "अन्य कट्टी कर", "2250", "tds", "both", {}),

    # Employee payables
    ("2261", "Salary and Wages Payable", "तलब तथा ज्याला भुक्तानी", "2260", "general", "both", {}),
    ("2262", "Provident Fund Payable", "सञ्चय कोष भुक्तानी", "2260", "general", "both", {}),
    ("2263", "Citizen Investment Trust Payable", "नागरिक लगानी कोष", "2260", "general", "both", {}),
    ("2264", "Social Security Fund Payable", "सामाजिक सुरक्षा कोष", "2260", "general", "both", {}),
    ("2265", "Staff Bonus Payable", "कर्मचारी बोनस भुक्तानी", "2260", "general", "both", {}),

    # Accruals and provisions
    ("2271", "Audit Fee Payable", "लेखापरीक्षण शुल्क भुक्तानी", "2270", "general", "both", {}),
    ("2272", "Rent Payable", "भाडा भुक्तानी", "2270", "general", "both", {}),
    ("2273", "Electricity and Water Payable", "बिजुली तथा पानी भुक्तानी", "2270", "general", "both", {}),
    ("2274", "Telephone and Internet Payable", "टेलिफोन तथा इन्टरनेट भुक्तानी", "2270", "general", "both", {}),
    ("2275", "Interest Payable", "ब्याज भुक्तानी", "2270", "general", "both", {}),
    ("2276", "Outstanding Expenses", "बाँकी खर्च", "2270", "general", "both", {}),
    ("2281", "Provision for Income Tax", "आयकर व्यवस्था", "2280", "general", "both", {}),
    ("2282", "Provision for Expenses", "खर्च व्यवस्था", "2280", "general", "both", {}),
    ("2283", "Provision for Audit Fee", "लेखापरीक्षण शुल्क व्यवस्था", "2280", "general", "both", {}),
    ("2291", "Sundry Payables", "विविध भुक्तानी", "2290", "general", "both", {}),
    ("2292", "Retention Money Payable", "धरौटी रकम भुक्तानी", "2290", "general", "both", {}),
    ("2293", "Unclaimed and Unpaid Amounts", "", "2290", "general", "both", {}),
    ("2294", "Security Deposit Received", "", "2290", "general", "both", {}),
    ("2295", "Lease Liability, Current Portion", "", "2290", "general", "both", {}),
    ("2296", "Current Portion of Long Term Borrowings", "", "2290", "general", "both",
     {"notes": "The instalments of a term loan falling due within twelve months belong "
               "in current liabilities under NAS 01."}),

    # Equity
    ("3101", "Proprietor Capital", "स्वामी पुँजी", "3100", "capital", "both", {}),
    ("3102", "Partner Capital", "साझेदार पुँजी", "3100", "capital", "both", {}),
    ("3103", "Share Capital", "शेयर पुँजी", "3100", "capital", "both", {}),
    ("3104", "Share Premium", "शेयर प्रिमियम", "3100", "capital", "both", {}),
    ("3105", "Partner Current Account", "साझेदार चल्ती खाता", "3100", "capital", "both", {}),

    ("3201", "Retained Earnings", "संचित मुनाफा", "3200", "capital", "both",
     {"is_system": 1, "notes": "Profit or loss of earlier years is carried here when a year is closed."}),
    ("3202", "Profit and Loss for the Year", "वर्षको नाफा नोक्सान", "3200", "capital", "both",
     {"is_system": 1, "notes": "Computed figure. Never posted to directly."}),
    ("3203", "General Reserve", "साधारण जगेडा", "3200", "capital", "both", {}),
    ("3204", "Revaluation Reserve", "पुनर्मूल्याङ्कन जगेडा", "3200", "capital", "both", {}),
    ("3205", "Capital Reserve", "पुँजीगत जगेडा", "3200", "capital", "both", {}),
    ("3301", "Drawings", "निकासी", "3300", "capital", "both", {}),

    # Revenue, goods
    ("4111", "Sales, Taxable", "बिक्री, करयोग्य", "4110", "sales", "trading",
     {"is_system": 1, "vat_rate_bp": 1300}),
    ("4112", "Sales, Exempt", "बिक्री, कर छुट", "4110", "sales", "trading", {"vat_rate_bp": 0}),
    ("4113", "Sales, Zero Rated and Export", "बिक्री, शून्य दर तथा निर्यात", "4110", "sales", "trading",
     {"vat_rate_bp": 0}),
    ("4114", "Sales, Cash Counter", "नगद काउन्टर बिक्री", "4110", "sales", "trading", {"vat_rate_bp": 1300}),

    # Revenue, services
    ("4121", "Audit and Assurance Fee", "लेखापरीक्षण शुल्क", "4120", "sales", "service",
     {"is_system": 1, "vat_rate_bp": 1300}),
    ("4122", "Taxation Service Fee", "कर सेवा शुल्क", "4120", "sales", "service", {"vat_rate_bp": 1300}),
    ("4123", "Accounting and Book Keeping Fee", "लेखा तथा हिसाब किताब शुल्क", "4120", "sales", "service",
     {"vat_rate_bp": 1300}),
    ("4124", "Company Secretarial and Compliance Fee", "कम्पनी सचिवीय शुल्क", "4120", "sales", "service",
     {"vat_rate_bp": 1300}),
    ("4125", "Advisory and Consultancy Fee", "सल्लाहकार शुल्क", "4120", "sales", "service",
     {"vat_rate_bp": 1300}),
    ("4126", "Certification and Attestation Fee", "प्रमाणीकरण शुल्क", "4120", "sales", "service",
     {"vat_rate_bp": 1300}),
    ("4127", "Training and Seminar Income", "तालिम तथा गोष्ठी आम्दानी", "4120", "sales", "service",
     {"vat_rate_bp": 1300}),
    ("4128", "Out of Pocket Recovery", "खर्च फिर्ता", "4120", "sales", "service", {}),

    ("4131", "Sales Return", "बिक्री फिर्ता", "4130", "contra_income", "both", {"is_system": 1}),
    ("4132", "Discount Allowed", "दिइएको छुट", "4130", "contra_income", "both", {}),

    # Other income
    ("4201", "Interest Income", "ब्याज आम्दानी", "4200", "general", "both", {}),
    ("4202", "Commission Income", "कमिशन आम्दानी", "4200", "general", "both", {}),
    ("4203", "Discount Received", "प्राप्त छुट", "4200", "general", "both", {}),
    ("4204", "Rental Income", "भाडा आम्दानी", "4200", "general", "both", {}),
    ("4205", "Gain on Sale of Fixed Assets", "सम्पत्ति बिक्रीबाट लाभ", "4200", "general", "both", {}),
    ("4206", "Foreign Exchange Gain", "विदेशी विनिमय लाभ", "4200", "general", "both", {}),
    ("4207", "Scrap Sales", "स्क्र्याप बिक्री", "4200", "general", "trading", {}),
    ("4208", "Write Back of Liabilities", "दायित्व फिर्ता", "4200", "general", "both", {}),
    ("4209", "Miscellaneous Income", "विविध आम्दानी", "4200", "general", "both", {}),

    # Purchases
    ("5101", "Purchase, Taxable", "खरिद, करयोग्य", "5100", "purchase", "trading",
     {"is_system": 1, "vat_rate_bp": 1300}),
    ("5102", "Purchase, Exempt", "खरिद, कर छुट", "5100", "purchase", "trading", {"vat_rate_bp": 0}),
    ("5103", "Purchase, Import", "खरिद, आयात", "5100", "purchase", "trading", {}),
    ("5104", "Purchase Return", "खरिद फिर्ता", "5100", "contra_expense", "trading", {"is_system": 1}),
    ("5105", "Discount on Purchase", "खरिदमा छुट", "5100", "contra_expense", "trading", {}),

    # Direct expenses
    ("5201", "Carriage Inward", "ढुवानी भित्र", "5200", "general", "trading", {}),
    ("5202", "Freight and Transport, Inward", "भाडा तथा ढुवानी", "5200", "general", "trading", {}),
    ("5203", "Custom Duty", "भन्सार महसुल", "5200", "general", "trading", {}),
    ("5204", "Clearing and Forwarding Charges", "क्लियरिङ तथा फर्वार्डिङ", "5200", "general", "trading", {}),
    ("5205", "Loading and Unloading", "लोडिङ अनलोडिङ", "5200", "general", "trading", {}),
    ("5206", "Direct Wages", "प्रत्यक्ष ज्याला", "5200", "general", "trading", {}),
    ("5207", "Assignment Direct Cost", "कार्य प्रत्यक्ष लागत", "5200", "general", "service", {}),
    ("5208", "Sub Contractor and Outsourcing Cost", "उप ठेकेदार लागत", "5200", "general", "both", {}),

    ("5401", "Cost of Goods Sold", "बेचिएको सामानको लागत", "5400", "general", "trading",
     {"is_system": 1,
      "notes": "Charged automatically as each sale is made, at the weighted average "
               "cost of the goods on the day they went out."}),
    ("5301", "Opening Stock", "प्रारम्भिक मौज्दात", "5300", "general", "trading", {"is_system": 1}),
    ("5302", "Closing Stock", "अन्तिम मौज्दात", "5300", "contra_expense", "trading", {"is_system": 1}),

    # Employee benefit
    ("6101", "Salary and Allowances", "तलब तथा भत्ता", "6100", "general", "both", {}),
    ("6102", "Wages", "ज्याला", "6100", "general", "trading", {}),
    ("6103", "Staff Bonus", "कर्मचारी बोनस", "6100", "general", "both", {}),
    ("6104", "Festival Allowance", "चाडपर्व खर्च", "6100", "general", "both", {}),
    ("6105", "Overtime", "अतिरिक्त समय भत्ता", "6100", "general", "both", {}),
    ("6106", "Provident Fund Contribution", "सञ्चय कोष योगदान", "6100", "general", "both", {}),
    ("6107", "Gratuity Expense", "उपदान खर्च", "6100", "general", "both", {}),
    ("6108", "Social Security Fund Contribution", "सामाजिक सुरक्षा कोष योगदान", "6100", "general", "both", {}),
    ("6109", "Leave Encashment", "बिदा भुक्तानी", "6100", "general", "both", {}),
    ("6110", "Staff Welfare", "कर्मचारी कल्याण", "6100", "general", "both", {}),
    ("6111", "Staff Training and Development", "कर्मचारी तालिम", "6100", "general", "both", {}),
    ("6112", "Staff Medical and Insurance", "कर्मचारी उपचार तथा बीमा", "6100", "general", "both", {}),
    ("6113", "Articled Trainee Stipend", "प्रशिक्षार्थी भत्ता", "6100", "general", "service", {}),

    # Administrative
    ("6201", "Office Rent", "कार्यालय भाडा", "6200", "general", "both", {"tds_section": "88", "tds_rate_bp": 1000}),
    ("6202", "Electricity and Water", "बिजुली तथा पानी", "6200", "general", "both", {}),
    ("6203", "Telephone, Mobile and Internet", "टेलिफोन तथा इन्टरनेट", "6200", "general", "both", {}),
    ("6204", "Repair and Maintenance, Building", "मर्मत सम्भार, भवन", "6200", "general", "both", {}),
    ("6205", "Repair and Maintenance, Equipment", "मर्मत सम्भार, उपकरण", "6200", "general", "both", {}),
    ("6206", "Repair and Maintenance, Vehicle", "मर्मत सम्भार, सवारी", "6200", "general", "both", {}),
    ("6207", "Fuel and Lubricants", "इन्धन", "6200", "general", "both", {}),
    ("6208", "Vehicle Running and Tax", "सवारी सञ्चालन तथा कर", "6200", "general", "both", {}),
    ("6209", "Printing and Stationery", "छपाइ तथा मसलन्द", "6200", "general", "both", {}),
    ("6210", "Postage and Courier", "हुलाक तथा कुरियर", "6200", "general", "both", {}),
    ("6211", "Office Expenses", "कार्यालय खर्च", "6200", "general", "both", {}),
    ("6212", "Cleaning and Sanitation", "सरसफाइ", "6200", "general", "both", {}),
    ("6213", "Security Expenses", "सुरक्षा खर्च", "6200", "general", "both", {}),
    ("6214", "Newspaper, Books and Periodicals", "पत्रपत्रिका तथा पुस्तक", "6200", "general", "both", {}),
    ("6215", "Legal and Professional Fee", "कानुनी तथा व्यावसायिक शुल्क", "6200", "general", "both",
     {"tds_section": "88", "tds_rate_bp": 1500}),
    ("6216", "Audit Fee", "लेखापरीक्षण शुल्क", "6200", "general", "both",
     {"tds_section": "88", "tds_rate_bp": 1500}),
    ("6217", "Consultancy Fee", "परामर्श शुल्क", "6200", "general", "both",
     {"tds_section": "88", "tds_rate_bp": 1500}),
    ("6218", "Registration and Renewal", "दर्ता तथा नवीकरण", "6200", "general", "both", {}),
    ("6219", "Membership and Subscription", "सदस्यता तथा शुल्क", "6200", "general", "both", {}),
    ("6220", "Insurance Premium", "बीमा शुल्क", "6200", "general", "both", {}),
    ("6221", "Bank Charges", "बैंक शुल्क", "6200", "general", "both", {}),
    ("6222", "Travelling and Conveyance, Local", "यात्रा तथा सवारी, आन्तरिक", "6200", "general", "both", {}),
    ("6223", "Travelling, Foreign", "विदेश भ्रमण", "6200", "general", "both", {}),
    ("6224", "Entertainment and Refreshment", "अतिथि सत्कार", "6200", "general", "both", {}),
    ("6225", "Meeting and Conference", "बैठक तथा सम्मेलन", "6200", "general", "both", {}),
    ("6226", "Donation and Charity", "दान तथा सहयोग", "6200", "general", "both",
     {"notes": "Deduction limited by section 12 of the Income Tax Act, 2058."}),
    ("6227", "Rates and Taxes", "कर तथा दस्तुर", "6200", "general", "both", {}),
    ("6228", "Software and Subscription", "सफ्टवेयर तथा सदस्यता", "6200", "general", "both", {}),
    ("6229", "Website and Hosting", "वेबसाइट तथा होस्टिङ", "6200", "general", "both", {}),
    ("6230", "Rent, Equipment", "उपकरण भाडा", "6200", "general", "both", {}),
    ("6231", "ICAN Membership and Practice Fee", "आइक्यान सदस्यता शुल्क", "6200", "general", "service", {}),
    ("6232", "Professional Indemnity Insurance", "व्यावसायिक क्षतिपूर्ति बीमा", "6200", "general", "service", {}),

    # Selling and distribution
    ("6301", "Advertisement and Publicity", "विज्ञापन तथा प्रचार", "6300", "general", "both", {}),
    ("6302", "Sales Promotion", "बिक्री प्रवर्धन", "6300", "general", "trading", {}),
    ("6303", "Commission on Sales", "बिक्री कमिशन", "6300", "general", "both",
     {"tds_section": "88", "tds_rate_bp": 1500}),
    ("6304", "Carriage Outward", "ढुवानी बाहिर", "6300", "general", "trading", {}),
    ("6305", "Packing and Forwarding", "प्याकिङ तथा फर्वार्डिङ", "6300", "general", "trading", {}),
    ("6306", "Bad Debts Written Off", "डुबेको रकम", "6300", "general", "both", {}),
    ("6307", "Provision for Doubtful Debts", "शंकास्पद ऋण व्यवस्था", "6300", "general", "both", {}),
    ("6308", "Warranty and After Sales Expense", "वारेन्टी खर्च", "6300", "general", "trading", {}),
    ("6309", "Business Promotion", "व्यवसाय प्रवर्धन", "6300", "general", "both", {}),

    # Finance cost
    ("7101", "Interest on Term Loan", "अवधि कर्जाको ब्याज", "7100", "general", "both", {}),
    ("7102", "Interest on Overdraft and Cash Credit", "ओभरड्राफ्ट ब्याज", "7100", "general", "both", {}),
    ("7103", "Interest to Related Party", "सम्बन्धित पक्षलाई ब्याज", "7100", "general", "both",
     {"tds_section": "88", "tds_rate_bp": 1500}),
    ("7104", "Loan Processing and Service Fee", "कर्जा प्रशोधन शुल्क", "7100", "general", "both", {}),
    ("7105", "Foreign Exchange Loss", "", "7100", "general", "both", {}),
    ("7106", "Interest on Lease Liability", "", "7100", "general", "both", {}),

    # Depreciation
    ("7201", "Depreciation on Building", "भवनको ह्रास", "7200", "general", "both", {}),
    ("7202", "Depreciation on Plant and Machinery", "", "7200", "general", "trading", {}),
    ("7203", "Depreciation on Furniture and Fixtures", "", "7200", "general", "both", {}),
    ("7204", "Depreciation on Office Equipment", "", "7200", "general", "both", {}),
    ("7205", "Depreciation on Computer", "", "7200", "general", "both", {}),
    ("7206", "Depreciation on Vehicles", "", "7200", "general", "both", {}),
    ("7207", "Amortisation of Intangible Assets", "", "7200", "general", "both", {}),
    ("7208", "Depreciation on Right of Use Asset", "", "7200", "general", "both", {}),
    ("7209", "Depreciation on Investment Property", "", "7200", "general", "both", {}),

    # Other expenses
    ("7301", "Loss on Sale of Fixed Assets", "सम्पत्ति बिक्रीमा नोक्सान", "7300", "general", "both", {}),
    ("7302", "Prior Period Expenses", "अघिल्लो अवधिको खर्च", "7300", "general", "both", {}),
    ("7303", "Penalty, Fine and Interest on Tax", "जरिवाना तथा कर ब्याज", "7300", "general", "both",
     {"notes": "Not deductible under section 21 of the Income Tax Act, 2058."}),
    ("7304", "Stock Written Off and Shortage", "मौज्दात नोक्सान", "7300", "general", "trading", {}),
    ("7305", "Rounding Off", "पूर्णांक फरक", "7300", "general", "both", {"is_system": 1}),
    ("7306", "Miscellaneous Expenses", "विविध खर्च", "7300", "general", "both", {}),

    # Tax
    ("8101", "Current Income Tax", "", "8100", "general", "both", {}),
    ("8102", "Deferred Tax Expense", "", "8100", "general", "both", {}),

    # Other comprehensive income. Items that never pass through profit or loss,
    # presented below it as NAS 01 requires.
    ("4301", "Revaluation Surplus on Property, Plant and Equipment", "", "4300", "general", "both",
     {"notes": "Will not be reclassified to profit or loss."}),
    ("4302", "Actuarial Gain or Loss on Defined Benefit Obligation", "", "4300", "general", "both",
     {"notes": "Will not be reclassified to profit or loss."}),
    ("4303", "Fair Value Change on Investments at Fair Value through OCI", "", "4300", "general", "both", {}),
    ("4304", "Income Tax relating to Other Comprehensive Income", "", "4300", "general", "both", {}),
]


VOUCHER_TYPES = [
    # code, name, nepali, prefix, affects_stock, affects_vat, vat_side, sort
    ("sales",        "Sales Invoice",       "बिक्री बीजक",      "SI", 1, 1, "output", 10),
    ("sales_return", "Sales Return",        "बिक्री फिर्ता",     "SR", 1, 1, "output", 20),
    ("purchase",     "Purchase Invoice",    "खरिद बीजक",       "PI", 1, 1, "input",  30),
    ("purchase_return", "Purchase Return",  "खरिद फिर्ता",      "PR", 1, 1, "input",  40),
    ("receipt",      "Receipt",             "रसिद",            "RV", 0, 0, "",       50),
    ("payment",      "Payment",             "भुक्तानी",         "PV", 0, 0, "",       60),
    ("contra",       "Contra",              "कन्ट्रा",          "CV", 0, 0, "",       70),
    ("journal",      "Journal",             "जर्नल",            "JV", 0, 0, "",       80),
    ("debit_note",   "Debit Note",          "डेबिट नोट",        "DN", 0, 1, "input",  90),
    ("credit_note",  "Credit Note",         "क्रेडिट नोट",       "CN", 0, 1, "output", 100),
    ("stock_adjust", "Stock Adjustment",    "मौज्दात मिलान",     "SA", 1, 0, "",      110),
    ("opening",      "Opening Balance",     "प्रारम्भिक मौज्दात", "OB", 0, 0, "",      120),
]


# Tax deducted at source, Income Tax Act 2058. Rates are the common ones a
# trading house or an audit practice deals with. Verify against the Finance Act
# of the year before relying on a rate for a filing.
TDS_SECTIONS = [
    ("87",     "Payment of employment income (as per slab)", 0, "Section 87"),
    ("88-rent", "Rent paid to a natural person", 1000, "Section 88(1)"),
    ("88-svc",  "Service fee, consultancy and professional fee", 1500, "Section 88(1)"),
    ("88-comm", "Commission", 1500, "Section 88(1)"),
    ("88-int",  "Interest to a natural person from bank or finance", 500, "Section 88(1)"),
    ("88-int-o", "Interest, other cases", 1500, "Section 88(1)"),
    ("88-div",  "Dividend paid by a resident company", 500, "Section 88(2)"),
    ("88-royal", "Royalty", 1500, "Section 88(1)"),
    ("89-contract", "Contract or agreement payment above the threshold", 150, "Section 89(1)"),
    ("89-vehicle", "Vehicle hire and carriage service", 250, "Section 89"),
    ("88-vat-svc", "Service fee paid to a VAT registered person", 150, "Section 88(1)"),
    ("95a",    "Advance tax on disposal of interest in land or building", 0, "Section 95Ka"),
]


UNITS = [
    ("Piece", "pcs", 0), ("Number", "no", 0), ("Set", "set", 0), ("Pair", "pair", 0),
    ("Box", "box", 0), ("Carton", "ctn", 0), ("Packet", "pkt", 0), ("Bundle", "bdl", 0),
    ("Dozen", "dzn", 0), ("Bag", "bag", 0), ("Roll", "roll", 0), ("Coil", "coil", 0),
    ("Kilogram", "kg", 3), ("Gram", "gm", 3), ("Quintal", "qtl", 3), ("Metric Ton", "mt", 3),
    ("Metre", "m", 3), ("Centimetre", "cm", 2), ("Foot", "ft", 2), ("Running Foot", "rft", 2),
    ("Square Metre", "sqm", 3), ("Square Foot", "sqft", 2), ("Cubic Metre", "cum", 3),
    ("Litre", "ltr", 3), ("Millilitre", "ml", 0), ("Gallon", "gal", 2),
    ("Hour", "hr", 2), ("Day", "day", 2), ("Month", "month", 2), ("Assignment", "job", 0),
]


ITEM_GROUPS_TRADING = [
    ("HW01", "Cement and Concrete", "सिमेन्ट तथा कंक्रिट"),
    ("HW02", "Steel, Rod and Binding Wire", "फलाम, रड तथा तार"),
    ("HW03", "Paint, Primer and Thinner", "रङ तथा सम्बन्धित"),
    ("HW04", "Pipe, Fitting and Sanitary", "पाइप तथा स्यानिटरी"),
    ("HW05", "Electrical and Wiring", "बिजुली सामग्री"),
    ("HW06", "Hardware, Nails and Fasteners", "किला तथा फास्टनर"),
    ("HW07", "Tools and Machinery", "औजार तथा मेसिन"),
    ("HW08", "Plywood, Board and Timber", "प्लाइउड तथा काठ"),
    ("HW09", "Tiles, Marble and Flooring", "टायल तथा मार्बल"),
    ("HW10", "Adhesive, Sealant and Chemical", "टाँस्ने तथा रसायन"),
    ("HW11", "Door, Window and Lock", "ढोका, झ्याल तथा ताल्चा"),
    ("HW12", "Safety and Miscellaneous", "सुरक्षा तथा विविध"),
]

ITEM_GROUPS_SERVICE = [
    ("SV01", "Audit and Assurance", "लेखापरीक्षण"),
    ("SV02", "Taxation", "कर सेवा"),
    ("SV03", "Accounting and Book Keeping", "लेखा सेवा"),
    ("SV04", "Company Secretarial", "कम्पनी सचिवीय"),
    ("SV05", "Advisory and Consultancy", "परामर्श"),
    ("SV06", "Certification", "प्रमाणीकरण"),
    ("SV07", "Training", "तालिम"),
]


def ledgers_for(business_type):
    """Return the ledger rows that apply to a trading house, a practice, or both."""
    wanted = {"both"}
    if business_type in ("trading", "both"):
        wanted.add("trading")
    if business_type in ("service", "both"):
        wanted.add("service")
    return [row for row in LEDGERS if row[5] in wanted]
