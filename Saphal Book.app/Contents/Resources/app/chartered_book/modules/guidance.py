"""
The rules this software is built around, gathered in one place.

This is a working aid, not authority. Rates and thresholds move with each
Finance Act, and the Act itself is amended. Anything here that carries a figure
should be checked against the current law before it is relied on in a return, a
set of accounts or an audit opinion. Where something changes often it says so.

Written for a practitioner who already knows the ground and wants the reference
to hand while entering, not an explanation from first principles.
"""

LAST_REVIEWED = "Bhadra 2083"

SECTIONS = [
    {
        "key": "year",
        "title": "The year, and what is due when",
        "summary": "Nepal runs on the Bikram Sambat year for tax and for accounts.",
        "items": [
            {"heading": "The income year",
             "body": "Shrawan 1 to the last day of Ashadh. Everything below is measured "
                     "against that, not the Gregorian year.",
             "reference": "Income Tax Act, 2058, section 2"},
            {"heading": "Income tax return",
             "body": "Due within three months of the end of the income year, so by the end "
                     "of Ashwin. The Department may extend it by up to a further three "
                     "months on an application made before the due date.",
             "reference": "Income Tax Act, 2058, sections 96 and 98"},
            {"heading": "Advance tax, in three instalments",
             "body": "By the end of Poush, forty percent of the estimated liability. By the "
                     "end of Chaitra, seventy percent. By the end of Ashadh, the whole of it. "
                     "Interest runs on a shortfall.",
             "reference": "Income Tax Act, 2058, section 94"},
            {"heading": "Value added tax return",
             "body": "Monthly for most, by the twenty fifth of the following month, with the "
                     "tax paid at the same time. Some taxpayers are permitted to file every "
                     "four months or every two months, which is set out in the registration.",
             "reference": "Value Added Tax Act, 2052, section 18"},
            {"heading": "Tax deducted at source",
             "body": "Deposited within twenty five days of the end of the month in which it "
                     "was withheld, with the statement filed at the same time.",
             "reference": "Income Tax Act, 2058, section 90"},
            {"heading": "Annual general meeting and the annual return",
             "body": "A public company holds its meeting within six months of the year end. "
                     "The annual return goes to the Office of the Company Registrar within "
                     "thirty days of the meeting. A private company files its return "
                     "annually whether or not it meets.",
             "reference": "Companies Act, 2063, sections 76, 78 and 80"},
        ],
    },
    {
        "key": "incometax",
        "title": "Income tax",
        "summary": "Rates, what is allowed, and what is added straight back.",
        "items": [
            {"heading": "The rate a company pays",
             "body": "Twenty five percent is the general rate. Thirty percent applies to "
                     "banks and financial institutions, insurance, telecommunication, "
                     "capital market business, and dealing in tobacco or liquor. Twenty "
                     "percent applies to a special industry, largely manufacturing. A "
                     "proprietorship is taxed on the slab rates for a natural person "
                     "instead.",
             "reference": "Income Tax Act, 2058, schedule 1",
             "caution": "The rates and the concessions on them change with almost every "
                        "Finance Act. Check the year before applying one."},
            {"heading": "Expenditure paid in cash",
             "body": "An expense paid in cash exceeding fifty thousand rupees to one person "
                     "in one transaction is not deductible, apart from the exceptions the "
                     "Act lists, which include payments to government bodies and to farmers, "
                     "and payments where banking is not available.",
             "reference": "Income Tax Act, 2058, section 21"},
            {"heading": "Fines, penalties and interest on tax",
             "body": "Not deductible. Add back in full when the return is prepared.",
             "reference": "Income Tax Act, 2058, section 21"},
            {"heading": "Donation",
             "body": "Deductible up to the lower of five percent of adjusted taxable income "
                     "or one hundred thousand rupees, and only where it goes to an exempt "
                     "organisation. Gifts to any other body are not deductible at all.",
             "reference": "Income Tax Act, 2058, section 12"},
            {"heading": "Repairs and improvement",
             "body": "Allowed up to seven percent of the depreciation base of the pool the "
                     "asset belongs to. Anything above that is capitalised into the pool and "
                     "written down with it.",
             "reference": "Income Tax Act, 2058, section 16"},
            {"heading": "Carrying a loss forward",
             "body": "Generally seven years. Longer for certain projects, including some "
                     "infrastructure and power. A loss cannot be carried back.",
             "reference": "Income Tax Act, 2058, section 20"},
            {"heading": "Where tax should have been deducted and was not",
             "body": "The expense is disallowed, and the person who should have withheld is "
                     "liable for the tax with interest. This is the single most common "
                     "adjustment on a small company assessment.",
             "reference": "Income Tax Act, 2058, sections 21 and 90"},
        ],
    },
    {
        "key": "tds",
        "title": "Tax deducted at source",
        "summary": "The rates a trading house or a practice meets most often.",
        "items": [
            {"heading": "Rent to a natural person", "body": "Ten percent.",
             "reference": "Income Tax Act, 2058, section 88"},
            {"heading": "Service fee, consultancy and professional fee",
             "body": "Fifteen percent. One and a half percent where the service is supplied "
                     "by a person registered for value added tax.",
             "reference": "Income Tax Act, 2058, section 88"},
            {"heading": "Commission", "body": "Fifteen percent.",
             "reference": "Income Tax Act, 2058, section 88"},
            {"heading": "Interest",
             "body": "Fifteen percent generally. Five percent on interest paid by a bank or "
                     "finance company to a natural person on a deposit.",
             "reference": "Income Tax Act, 2058, section 88"},
            {"heading": "Dividend from a resident company", "body": "Five percent, and final.",
             "reference": "Income Tax Act, 2058, section 88"},
            {"heading": "Contract or agreement payment",
             "body": "One and a half percent where the payment to one person exceeds fifty "
                     "thousand rupees in the income year.",
             "reference": "Income Tax Act, 2058, section 89"},
            {"heading": "Employment income",
             "body": "Withheld each month against the slab rates, with the social security "
                     "tax and any allowable deductions taken into account.",
             "reference": "Income Tax Act, 2058, section 87"},
        ],
        "caution": "Rates move with the Finance Act. Confirm the rate for the year before "
                   "filing anything.",
    },
    {
        "key": "vat",
        "title": "Value added tax",
        "summary": "Registration, the invoice itself, and what has to be kept.",
        "items": [
            {"heading": "The rate", "body": "Thirteen percent. Exports are zero rated. "
                     "Schedule 1 lists what is exempt, which includes basic agricultural "
                     "produce, certain education and health services and some financial "
                     "services.",
             "reference": "Value Added Tax Act, 2052, section 7 and schedules 1 and 2"},
            {"heading": "When registration becomes compulsory",
             "body": "Once taxable turnover crosses the threshold set for goods, or the "
                     "lower one set for services and mixed supply. Some businesses must "
                     "register whatever their turnover, and registration may also be taken "
                     "voluntarily.",
             "reference": "Value Added Tax Act, 2052, section 10",
             "caution": "The thresholds have been changed several times. Check the figure "
                        "in force for the year rather than working from memory."},
            {"heading": "What a tax invoice must show",
             "body": "The words tax invoice, the seller's name, address and registration "
                     "number, the buyer's name, address and registration number, a serial "
                     "number and the date, a description with quantity and value, the tax "
                     "shown separately, and which copy the sheet is. The original goes to "
                     "the buyer and the copy stays.",
             "reference": "Value Added Tax Rules, 2053, rule 17"},
            {"heading": "Records to keep",
             "body": "A purchase book and a sales book in the prescribed form, with the "
                     "invoices behind them, kept for six years.",
             "reference": "Value Added Tax Act, 2052, section 16"},
            {"heading": "Credit that cannot be claimed",
             "body": "Input tax on a motor vehicle, on entertainment, and on beverages is "
                     "restricted. Input tax on a purchase used for an exempt supply cannot "
                     "be claimed at all, and a mixed use has to be apportioned.",
             "reference": "Value Added Tax Act, 2052, section 17"},
            {"heading": "Carrying credit forward",
             "body": "Excess credit is carried into the following month. A refund may be "
                     "claimed once credit has been carried continuously for the period the "
                     "Act sets, and immediately by an exporter meeting the export condition.",
             "reference": "Value Added Tax Act, 2052, sections 17 and 24"},
        ],
    },
    {
        "key": "companies",
        "title": "Companies Act, 2063",
        "summary": "What a company has to keep, have audited and file.",
        "items": [
            {"heading": "Books of account",
             "body": "Kept at the registered office, on a double entry basis, giving a true "
                     "and fair view, and retained for at least five years.",
             "reference": "Companies Act, 2063, section 108"},
            {"heading": "Accounts and audit",
             "body": "The board prepares the annual financial statements within six months "
                     "of the year end and has them audited. Every company must appoint an "
                     "auditor, who has to hold a certificate of practice from the Institute "
                     "of Chartered Accountants of Nepal.",
             "reference": "Companies Act, 2063, sections 108 and 111"},
            {"heading": "Who cannot audit",
             "body": "A partner or employee of the company, a debtor of it, anyone convicted "
                     "of an offence involving moral turpitude, a substantial shareholder, "
                     "and anyone else the Act names. An auditor may not hold office for more "
                     "than three consecutive terms in a public company.",
             "reference": "Companies Act, 2063, section 112"},
            {"heading": "Filing with the Registrar",
             "body": "The audited statements, the auditor's report and the directors' report "
                     "go to the Office of the Company Registrar with the annual return. A "
                     "private company that has not held a meeting still files annually.",
             "reference": "Companies Act, 2063, section 80"},
            {"heading": "A small private company",
             "body": "The Act allows a lighter regime for a private company below the size "
                     "the Registrar prescribes, but the requirement to keep proper books and "
                     "to be audited is not removed.",
             "reference": "Companies Act, 2063"},
            {"heading": "Appointing the auditor",
             "body": "The first auditor is appointed by the board. After that the general "
                     "meeting appoints, and fixes the remuneration, and the appointment runs "
                     "until the next annual general meeting. An auditor who is not "
                     "reappointed, or who is removed, is entitled to be heard first.",
             "reference": "Companies Act, 2063, sections 110, 111 and 113"},
            {"heading": "What the auditor has to report on",
             "body": "More than the opinion. Whether the information and explanations asked "
                     "for were obtained, whether the books have been kept as the Act "
                     "requires, whether the statements agree with those books and give a "
                     "true and fair view, whether the business was conducted "
                     "satisfactorily, and whether the board or any employee has acted "
                     "contrary to law or caused loss to the company. That last one has no "
                     "equivalent in the international form of report and is easy to leave "
                     "out.",
             "reference": "Companies Act, 2063, section 115"},
            {"heading": "Directors' report",
             "body": "Goes to the annual general meeting alongside the audited statements "
                     "and covers the year under review, the state of the business, changes "
                     "in the board, what has happened since the year end and what the "
                     "directors have to say about the auditor's remarks.",
             "reference": "Companies Act, 2063, section 109"},
            {"heading": "Dividend",
             "body": "Declared out of profit available for distribution, not out of capital "
                     "and not while accumulated losses stand. Tax deducted at source on "
                     "dividend is a final tax for a natural person.",
             "reference": "Companies Act, 2063, section 182; Income Tax Act, 2058, section 88"},
            {"heading": "Loans to directors",
             "body": "A company may not lend to its own director, nor give a guarantee or "
                     "security for a loan taken by one. If a director's account is in debit "
                     "it is worth establishing what it really is before it is signed off.",
             "reference": "Companies Act, 2063, sections 105 and 106"},
            {"heading": "Losing half the capital",
             "body": "Where accumulated losses have taken half the share capital or more, "
                     "the directors have to put it to the shareholders. It is also a going "
                     "concern matter for the statements, not only a company law one.",
             "reference": "Companies Act, 2063; NAS 01"},
        ],
    },
    {
        "key": "auditact",
        "title": "Audit Act, 2048",
        "summary": "Who the Auditor General audits, and what that audit covers.",
        "items": [
            {"heading": "What it governs",
             "body": "The audit of the public purse. It is a different regime from the "
                     "Companies Act: the auditor is the Auditor General rather than a firm "
                     "appointed by the shareholders, and the audit answers to the "
                     "legislature rather than to the owners.",
             "reference": "Constitution of Nepal, Part 22; Audit Act, 2048"},
            {"heading": "Who is audited",
             "body": "Government offices, the courts, constitutional bodies, the army and "
                     "the police, and corporate bodies fully owned by the Government of "
                     "Nepal. Where a body is substantially but not fully owned, the auditor "
                     "is appointed in consultation with the Auditor General.",
             "reference": "Audit Act, 2048"},
            {"heading": "What the audit covers",
             "body": "Wider than an opinion on the statements. Regularity, meaning whether "
                     "the money was spent with authority and within the appropriation, and "
                     "economy, efficiency and effectiveness, meaning whether it achieved "
                     "anything. Propriety runs through all of it.",
             "reference": "Audit Act, 2048"},
            {"heading": "How the report is made",
             "body": "The Auditor General reports annually to the President, who causes it "
                     "to be laid before the Federal Parliament. Irregularities that are not "
                     "cleared are carried in that report and pursued through the Public "
                     "Accounts Committee.",
             "reference": "Constitution of Nepal, article 294"},
            {"heading": "Where a firm comes into it",
             "body": "The Auditor General may engage licensed auditors to carry out or "
                     "assist with an audit, under the Auditor General's direction and "
                     "standards. The engagement does not make the firm the statutory "
                     "auditor: the report remains the Auditor General's.",
             "reference": "Audit Act, 2048"},
            {"heading": "Standards applied",
             "body": "Public sector audit in Nepal follows the Auditor General's own "
                     "directives and the international public sector standards, which are "
                     "not the same as the Nepal Standards on Auditing used for a company "
                     "audit. Do not carry a company audit file across to one of these "
                     "without checking what changes.",
             "reference": "Audit Act, 2048; ISSAI"},
        ],
    },
    {
        "key": "standards",
        "title": "Accounting standards",
        "summary": "Which framework applies, and the standards that come up most.",
        "items": [
            {"heading": "Which framework",
             "body": "Nepal Financial Reporting Standards apply to listed companies, banks "
                     "and financial institutions, insurance companies and other public "
                     "interest entities. NFRS for Small and Medium sized Entities applies to "
                     "most other companies. A very small entity may use the simpler basis "
                     "the Accounting Standards Board allows. Say in the accounts which one "
                     "has been followed.",
             "reference": "Accounting Standards Board Nepal"},
            {"heading": "NAS 01, presentation",
             "body": "A complete set is the statement of financial position, the statement "
                     "of profit or loss and other comprehensive income, the statement of "
                     "changes in equity, the statement of cash flows, and the notes, each "
                     "with comparatives.",
             "reference": "NAS 01"},
            {"heading": "NAS 02, inventories",
             "body": "The lower of cost and net realisable value. Cost on first in first out "
                     "or weighted average, applied consistently. Last in first out is not "
                     "permitted.",
             "reference": "NAS 02"},
            {"heading": "NAS 07, cash flows",
             "body": "Operating, investing and financing, by the direct or the indirect "
                     "method. Cash equivalents are short term, highly liquid and subject to "
                     "insignificant risk of change in value.",
             "reference": "NAS 07"},
            {"heading": "NAS 12, income taxes",
             "body": "Deferred tax on temporary differences, measured at the rate expected "
                     "to apply when the difference reverses. The commonest difference in a "
                     "Nepali trading company is between book depreciation and the pool "
                     "depreciation the Income Tax Act allows.",
             "reference": "NAS 12"},
            {"heading": "NAS 16, property, plant and equipment",
             "body": "Recognised at cost, then carried at cost less accumulated depreciation "
                     "and impairment, or at a revalued amount. Depreciated over the useful "
                     "life, which is an accounting judgement and need not match the tax "
                     "class.",
             "reference": "NAS 16"},
            {"heading": "NFRS 15, revenue",
             "body": "Revenue when control passes, measured at the price expected to be "
                     "received, net of discounts and returns.",
             "reference": "NFRS 15"},
            {"heading": "NFRS 9 and NFRS 7, financial instruments",
             "body": "Classified and measured by the business model and the cash flow "
                     "characteristics, with a loss allowance on the expected credit loss "
                     "basis. NFRS 7 sets out what has to be disclosed, including the "
                     "categories, the maturity profile and the concentrations of risk.",
             "reference": "NFRS 9 and NFRS 7"},
        ],
    },
    {
        "key": "payroll",
        "title": "Employment costs",
        "summary": "What has to be contributed and paid on top of wages.",
        "items": [
            {"heading": "Provident fund and gratuity",
             "body": "Under the Labour Act, 2074 the employer contributes ten percent of "
                     "basic salary to provident fund alongside the employee's ten percent, "
                     "and gratuity accrues at eight point three three percent of basic "
                     "salary.",
             "reference": "Labour Act, 2074"},
            {"heading": "Social security fund",
             "body": "Where the entity is enrolled, the contribution is thirty one percent "
                     "of basic salary, eleven from the employee and twenty from the "
                     "employer, and it replaces the separate provident fund and gratuity "
                     "arrangements.",
             "reference": "Contribution Based Social Security Act, 2074"},
            {"heading": "Bonus",
             "body": "Ten percent of net profit is set aside as bonus, distributed to "
                     "employees on the basis the Act sets, with the residue going to the "
                     "welfare fund and the national welfare fund.",
             "reference": "Bonus Act, 2030"},
            {"heading": "Leave",
             "body": "Annual leave accrues at one day for every twenty worked and sick leave "
                     "at twelve days a year on half pay, with limits on accumulation and on "
                     "encashment.",
             "reference": "Labour Act, 2074"},
        ],
    },
    {
        "key": "audit",
        "title": "Doing the audit",
        "summary": "The order the work goes in, and what has to be on the file.",
        "items": [
            {"heading": "Before accepting",
             "body": "Check independence, check the previous auditor has been communicated "
                     "with, agree the terms in an engagement letter, and satisfy yourself the "
                     "preconditions for an audit are present.",
             "reference": "NSA 210 and 220"},
            {"heading": "Understanding and risk",
             "body": "Understand the entity and its controls, identify where the statements "
                     "could be materially misstated, and design the work to respond to that "
                     "rather than to a standard programme.",
             "reference": "NSA 315 and 330"},
            {"heading": "Materiality",
             "body": "Set it for the statements as a whole, set performance materiality below "
                     "it, and set a lower figure for any class of transaction where a smaller "
                     "misstatement would still influence a reader. Record the basis.",
             "reference": "NSA 320"},
            {"heading": "Fraud",
             "body": "Presume a risk of fraud in revenue recognition, test journal entries, "
                     "review accounting estimates for bias, and understand the business "
                     "rationale of anything significant outside the normal course.",
             "reference": "NSA 240"},
            {"heading": "Analytical procedures",
             "body": "Required at the planning stage and again at the end, when the "
                     "statements are read as a whole to see whether they are consistent with "
                     "what the auditor now knows.",
             "reference": "NSA 520"},
            {"heading": "Documentation",
             "body": "Enough that an experienced auditor with no previous connection could "
                     "understand the work done, the evidence obtained and the conclusions "
                     "reached. Assemble the file within sixty days of the report.",
             "reference": "NSA 230"},
            {"heading": "Going concern and subsequent events",
             "body": "Consider whether the going concern basis is appropriate for at least "
                     "twelve months from the date of approval, and deal with what has "
                     "happened between the year end and the report.",
             "reference": "NSA 570 and 560"},
            {"heading": "Reporting",
             "body": "Form the opinion, and where it is modified say plainly why and what the "
                     "effect is. Key audit matters are communicated where required. The "
                     "report also covers what the Companies Act, 2063 requires an auditor in "
                     "Nepal to state.",
             "reference": "NSA 700, 701 and 705"},
        ],
    },
]
