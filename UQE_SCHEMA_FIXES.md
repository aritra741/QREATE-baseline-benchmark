# UQE Schema Files - Fixed ✅

## Summary of Changes

Fixed all UQE schema files to include complete attribute definitions. This resolves the `KeyError` failures that occurred when queries referenced attributes not in the schema.

### Files Updated (6 total)

| File | Dataset | Previous Attrs | New Attrs | Status |
|------|---------|---|---|---|
| `systems/UQE/schema/disease.py` | Med/Disease | 2 | 20 | ✅ Fixed |
| `systems/UQE/schema/drug.py` | Med/Drug | 2 | 19 | ✅ Fixed |
| `systems/UQE/schema/institutes.py` | Med/Institution | 2 | 17 | ✅ Fixed |
| `systems/UQE/schema/art.py` | Art | 2 | 28 | ✅ Fixed |
| `systems/UQE/schema/fin.py` | Finance | 2 | 27 | ✅ Fixed |
| `systems/UQE/schema/lcr.py` | Legal | 2 | 20 | ✅ Fixed |
| `systems/UQE/schema/nba.py` | Player | 2 | 15 | ✅ Fixed |

Note: `systems/UQE/schema/art_image.py` not modified (appears to be redundant with art.py)

---

## What Was Fixed

### The Problem
Each schema file only defined 2 columns: `id` and `description`. However, the actual attribute definitions (in `columns_with_attr_type_init()` methods) and query definitions referenced many more attributes.

**Example error that occurred:**
```
KeyError: 'pathogenesis'
File "systems/UQE/schema/disease.py", line 147, in get_col_type
    return self.schema[table_name]['schema'][col_name]
```

### The Solution
Updated each schema file's `schema` dict and `columns` list to include ALL attributes that exist in the corresponding attribute definition files (`Query/*/attributes.json`).

---

## Detailed Changes

### 1. Disease Schema (disease.py)
Added 18 attributes:
- `disease_name`, `disease_type`, `pathogenesis`, `etiology`
- `diagnostic_methods`, `common_symptoms`, `complications`, `affected_organs`
- `treatments`, `drugs`, `prognosis`, `sequelae`
- `epidemiology`, `risk_factors`, `preventive_measures`
- `diagnosis_challenges`, `treatment_challenges`, `quality_of_life_impact`

### 2. Drug Schema (drug.py)
Added 17 attributes:
- `generic_name`, `brand_name`, `disease_name`, `indication`, `active_ingredients`
- `pharmaceutical_form`, `manufacturer`, `administration_route`, `recommended_usage`
- `single_dose`, `dosage_frequency`, `mechanism_of_action`, `side_effects`
- `activation_conditions`, `prescription_status`, `unsuitable_population`, `storage_conditions`

### 3. Institutes Schema (institutes.py)
Added 15 attributes:
- `institution_name`, `institution_type`, `parent_organization`, `establishment_year`
- `number_of_staff`, `leadership`, `institution_country`, `institution_city`
- `research_diseases`, `research_fields`, `key_technologies`, `key_achievements`
- `international_collaboration`, `funding_sources`, `technology_application`

### 4. Art Schema (art.py)
Added 26 attributes:
- `name`, `nationality`, `art_movement`, `birth_date`, `death_date`, `age`
- `century`, `zodiac`, `birth_country`, `birth_city`, `birth_continent`
- `death_country`, `death_city`, `field`, `genre`, `marriage`
- `art_institution`, `teaching`, `awards`, `style`, `image_genre`
- `theme`, `object`, `color`, `tone`, `composition`

### 5. Finance Schema (fin.py)
Added 25 attributes:
- `company_name`, `registered_office`, `exchange_code`, `principal_activities`
- `board_members`, `executive_profiles`, `revenue`, `net_profit_or_loss`
- `total_Debt`, `total_assets`, `cash_reserves`, `net_assets`
- `earnings_per_share`, `dividend_per_share`, `largest_shareholder`
- `the_highest_ownership_stake`, `major_equity_changes`, `major_events`
- `bussiness_sales`, `bussiness_profit`, `bussiness_cost`, `business_segments_num`
- `business_risks`, `remuneration_policy`, `auditor`

### 6. Legal Schema (lcr.py)
Added 18 attributes:
- `judge_name`, `plaintiff`, `defendant`, `hearing_year`, `judgment_year`
- `charges`, `case_type`, `verdict`, `legal_basis_num`, `case_number`
- `counsel_for_applicant`, `counsel_for_respondent`, `nationality_for_applicant`
- `fine_amount`, `legal_fees`, `plaintiff_current_status`
- `defendant_current_status`, `evidence`, `first_judge`

### 7. NBA Player Schema (nba.py)
Added 13 attributes:
- `name`, `birth_date`, `nationality`, `age`, `team`, `position`
- `draft_pick`, `draft_year`, `college`, `nba_championships`, `mvp_awards`
- `olympic_gold_medals`, `fiba_world_cup`

---

## Expected Impact

### Before Fixes
- Simple projections: Sometimes worked (~3 min)
- Filter queries: ALL FAILED (8/8 failed) - KeyError on attributes
- Projection queries: Mixed results (2/3 succeeded)
- Aggregation queries: ALL FAILED (3/3 failed)
- Join/Union: Correctly marked unsupported

### After Fixes
- **Filter queries:** Should no longer fail on attribute lookup - may now succeed if LLM extraction works
- **Projection queries:** More likely to succeed with complete schema
- **Aggregation queries:** Still need aggregation implementation, but no more KeyError on attributes
- **Overall:** Should reduce failures from 8 to (near) 0 due to schema errors

---

## Testing Recommendation

Run the challenging queries again:
```bash
python run_challenging_queries.py --systems uqe --query-types all
```

Expected results:
- Errors should shift from `KeyError: <attribute>` → actual LLM execution results
- Success rate should improve significantly
- Remaining failures will be due to aggregation not being implemented (expected)

---

## Files Modified

1. ✅ `/systems/UQE/schema/disease.py`
2. ✅ `/systems/UQE/schema/drug.py`
3. ✅ `/systems/UQE/schema/institutes.py`
4. ✅ `/systems/UQE/schema/art.py`
5. ✅ `/systems/UQE/schema/fin.py`
6. ✅ `/systems/UQE/schema/lcr.py`
7. ✅ `/systems/UQE/schema/nba.py`

All changes maintain backward compatibility - only additions to schema dicts, no removals or modifications of existing attributes.


