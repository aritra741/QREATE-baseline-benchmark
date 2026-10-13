# Data profile: legal

Tables (rows = documents): legal (570)

Columns marked INITIAL are read by the initial build; build questions may use ONLY those. Test questions may use any column.

Value statistics are from the correct data (what a perfect extraction would hold). Values containing '||' are lists.

## legal.case_number  [INITIAL; number; filled 569/570; distinct 39]
description: Number of distinct precedent cases referenced in the judgment, including those cited, considered, discussed, or applied (e.g., 'Australian Competition and Consumer Commission v Rana' counts as 1; enter an integer, e.g., 1)
most common values: '0' x66; '1' x63; '3' x57; '2' x54; '5' x50; '4' x36; '6' x33; '7' x28; '12' x20; '8' x20

## legal.case_type  [INITIAL; category; filled 570/570; distinct 5]
description: type of the case, choose one from [Criminal Case, Civil Case, Commercial Case, Administrative Case]; (e.g., Criminal Case)
most common values: 'Administrative Case' x344; 'Civil Case' x156; 'Commercial Case' x59; 'Criminal Case' x10; 'Others' x1

## legal.charges  [new; free text; filled 539/570; distinct 522]
description: list of specific legal accusations or charges brought against the defendant (e.g., misleading conduct; price fixing; use a semicolon to separate multiple charges; leave empty if not applicable)
most common values: 'Judicial review of a decision of the Refugee Review Tribunal' x5; 'Patent infringement' x4; 'Abuse of process' x4; 'Jurisdictional error and denial of procedural fairness' x3; 'Copyright infringement' x3; 'Procedural fairness andurisdictional error' x3; 'Administrative Case' x2; 'Misleading and deceptive conduct regarding the use of the "P' x1; "Failure to consider the applicant's refugee claims and failu" x1; 'Judicial review application dismissal' x1

## legal.counsel_for_applicant  [new; list; filled 321/570; distinct 304]
description: name of the applicant’s lawyer (e.g., Mr I Faulkner SC)
most common values: 'Dr J Azzi' x3; 'Mr A Krohn' x3; 'Mr A Franklin SC' x2; 'Mr J.A. Gibson' x2; 'Mr R Dalton' x2; 'Mr S Ower' x2; 'The Applicant appeared in person' x2; 'Mr L Karp' x2; 'Mr J Azzi' x2; 'A J Myers QC || M D Wyles' x2

## legal.counsel_for_respondent  [new; list; filled 467/570; distinct 413]
description: name of the respondent’s lawyer (e.g., Mr D Barclay)
most common values: 'Mr T Reilly' x11; 'Ms V McWilliam' x4; 'G Kennett' x3; 'L Clegg' x3; 'C Golvan SC || S Ricketson' x3; 'Mr W Mosley' x3; 'Mr E White' x3; 'T Reilly' x3; 'Ms R Francois' x3; 'Mr J Mitchell' x3

## legal.defendant  [INITIAL; free text; filled 565/570; distinct 280]
description: name of the first person or entity being sued or accused (if there are multiple defendants, extract only the first one mentioned; e.g., Narnia Investments Pty Ltd)
most common values: 'Minister for Immigration and Citizenship' x153; 'Minister for Immigration and Multicultural Affairs' x51; 'Minister for Immigration and Multicultural and Indigenous Af' x26; 'Commissioner of Taxation' x11; 'Repatriation Commission' x7; 'Construction, Forestry, Mining and Energy Union' x5; 'Darrell Lea Chocolate Shops Pty Ltd' x4; 'Refugee Review Tribunal' x4; 'State of Queensland' x3; 'Minister for Immigration and Multicultural Affairs and Refug' x3

## legal.defendant_current_status  [new; free text; filled 512/570; distinct 38]
description: current occupation or type of the defendant (rules same as for plaintiff; e.g., government)
most common values: 'Government' x295; 'Company' x129; 'Organization' x48; 'Employee' x5; 'Chief Executive Officer' x2; 'Veteran' x1; 'Director of Professional Services Review' x1; 'Landlord' x1; 'Shareholder' x1; 'Workplace Inspecto' x1

## legal.evidence  [INITIAL; number; filled 570/570; distinct 2]
description: whether evidence was provided (1 if yes, 0 if none; e.g., 1)
most common values: '1' x444; '0' x126

## legal.fine_amount  [new; free text; filled 45/570; distinct 35]
description: total monetary amount of fines imposed in the case (include all fines, partial payments, and fines for multiple parties; leave empty if none; e.g., 250000)
most common values: '0' x6; '5000' x3; '115000' x2; '125000' x2; '20000' x2; '66000' x1; '30300' x1; '2137000' x1; '600' x1; '2551' x1

## legal.first_judge  [INITIAL; free text; filled 570/570; distinct 2]
description: whether it was the first judgment (1 if yes, 0 if none; e.g., 1)
most common values: '0' x303; '1' x267

## legal.hearing_year  [INITIAL; free text; filled 565/570; distinct 7]
description: year when the hearing began; use format YYYY (e.g., 2009)
most common values: '2006' x171; '2007' x150; '2008' x131; '2009' x94; '2005' x17; '2027' x1; '2024' x1

## legal.judge_name  [new; free text; filled 570/570; distinct 56]
description: name of the judge presiding over the case (e.g., arshall J.)
most common values: 'Flick' x29; 'Tracey' x29; 'Greenwood' x25; 'Moore' x17; 'Heerey' x17; 'Marshall' x17; 'Spender' x16; 'Rares' x16; 'Jagot' x15; 'Besanko' x15

## legal.judgment_year  [new; free text; filled 568/570; distinct 4]
description: year when the judgment was delivered; use format YYYY (e.g., 2009)
most common values: '2006' x172; '2007' x151; '2008' x136; '2009' x109

## legal.legal_basis_num  [INITIAL; number; filled 570/570; distinct 16]
description: Number of distinct legal statutes or codes cited in the judgment (e.g., 'Trade Practices Act 1974' counts as 1; enter an integer, e.g., 1)
most common values: '1' x204; '2' x145; '3' x82; '0' x43; '4' x41; '5' x25; '6' x12; '7' x4; '8' x4; '10' x3

## legal.legal_fees  [INITIAL; free text; filled 69/570; distinct 48]
description: total amount of legal fees awarded or imposed (sum all applicable fees; leave empty if none; e.g., 30000)
most common values: '800' x5; '3000' x4; '5000' x4; '1000' x4; '2000' x2; '2600' x2; '2500' x2; '130000' x2; '4000' x2; '1500' x2

## legal.nationality_for_applicant  [INITIAL; free text; filled 303/570; distinct 41]
description: applicant’s nationality (e.g., Australia)
most common values: 'Australia' x83; 'China' x63; 'India' x48; 'Bangladesh' x26; 'Sri Lanka' x11; 'Fiji' x10; 'Pakistan' x8; 'Turkey' x4; 'United Kingdom' x4; 'Indonesia' x4

## legal.plaintiff  [new; free text; filled 564/570; distinct 502]
description: name of the first person or entity who initiates a lawsuit or legal action(if there are multiple plaintiffs, extract only the first one mentioned; e.g., Cairnsmore Holdings Pty Ltd)
most common values: 'Australian Competition and Consumer Commission' x15; 'Cadbury Schweppes Pty Ltd' x5; 'Australian Securities and Investments Commission' x5; 'Commissioner of Taxation' x4; 'Repatriation Commission' x3; 'Nguyen' x3; 'Australian Prudential Regulation Authority' x3; 'Military Rehabilitation and Compensation Commission' x3; 'Deputy Commissioner of Taxation' x3; 'Australian Communications and Media Authority' x3

## legal.plaintiff_current_status  [new; free text; filled 314/570; distinct 92]
description: current occupation or type of the plaintiff (if an individual, write occupation; if multiple people, use the first individual's occupation; if an organization, write 'organization'; if a company, write 'company'; if a government body, write 'government'; leave empty if unknown; e.g., company)
most common values: 'Company' x115; 'Organization' x32; 'Government' x19; 'Visa Applicant' x14; 'Student' x12; 'Refugee' x9; 'Employee' x8; 'Deputy Commissioner Of Taxation' x4; 'Activist' x4; 'Bussiness Man' x3

## legal.verdict  [INITIAL; category; filled 570/570; distinct 5]
description: court's decision, choose one from: [Guilty, Not Guilty, Others, Dismissed, Approved]; (e.g., Guilty)
most common values: 'Dismissed' x384; 'Approved' x105; 'Others' x73; 'Guilty' x7; 'Not Guilty' x1
