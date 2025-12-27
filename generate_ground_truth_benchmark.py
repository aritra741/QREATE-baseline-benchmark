#!/usr/bin/env python3
"""
Generate ground truth CSV files for all 17 challenging queries.

This generates ground truth INDEPENDENT of any specific run_id.
Ground truth = executing the actual SQL queries against the raw data.
"""

import pandas as pd
import json
from pathlib import Path
import re

PROJECT_ROOT = Path('.')

# Ground truth raw data paths
RAW_DATA = {
    'Med': {
        'disease': 'Data/Med/disease.csv',
        'drug': 'Data/Med/drug.csv',
        'institution': 'Data/Med/institution.csv'
    },
    'Player': {
        'player': 'Data/Player/player.csv',
        'team': 'Data/Player/team.csv',
        'manager': 'Data/Player/manager.csv',
        'city': 'Data/Player/city.csv'
    },
    'Art': {
        'art': 'raw/ground_truth/WikiArt/wikiart.csv'
    },
    'Legal': {
        'legal_case': 'Data/Legal/Legal.csv'
    },
    'Finan': {
        'financial_record': 'Data/Finan/Finan.csv',
        'finance': 'Data/Finan/Finan.csv'
    }
}

# The 17 challenging queries (from run_challenging_queries.py)
QUERIES = [
    # Simple (2)
    {
        'id': 'simple_1',
        'type': 'simple',
        'dataset': 'Med',
        'entity': 'disease',
        'sql': "SELECT disease_name, disease_type FROM disease"
    },
    {
        'id': 'simple_2',
        'type': 'simple',
        'dataset': 'Player',
        'entity': 'player',
        'sql': "SELECT name, nationality, position FROM player"
    },
    
    # Filter (3)
    {
        'id': 'filter_1',
        'type': 'filter',
        'dataset': 'Med',
        'entity': 'disease',
        'sql': """SELECT disease_name, pathogenesis, prognosis, quality_of_life_impact, treatment_challenges
                FROM disease
                WHERE pathogenesis = 'autoimmune' 
                  AND prognosis = 'chronic_condition' 
                  AND quality_of_life_impact = 'work_disability'
                  AND treatment_challenges != 'drug resistance'"""
    },
    {
        'id': 'filter_2',
        'type': 'filter',
        'dataset': 'Legal',
        'entity': 'legal_case',
        'sql': """SELECT judge_name, plaintiff, defendant, charges, first_judge, case_number, verdict
                FROM Legal_Case
                WHERE first_judge = '1' 
                  AND case_type = 'Commercial Case'
                  AND case_number >= 10
                  AND fine_amount != '20000.00'"""
    },
    {
        'id': 'filter_3',
        'type': 'filter',
        'dataset': 'Art',
        'entity': 'art',
        'sql': """SELECT name, art_movement, birth_country, birth_city
                FROM art
                WHERE marriage = 'Divorced'
                  AND century = '20th'"""
    },
    
    # Projection (3)
    {
        'id': 'projection_1',
        'type': 'projection',
        'dataset': 'Finan',
        'entity': 'financial_record',
        'sql': "SELECT principal_activities, revenue, net_profit_or_loss FROM financial_record"
    },
    {
        'id': 'projection_2',
        'type': 'projection',
        'dataset': 'Med',
        'entity': 'disease',
        'sql': "SELECT disease_name, pathogenesis, prognosis FROM disease"
    },
    {
        'id': 'projection_3',
        'type': 'projection',
        'dataset': 'Art',
        'entity': 'art',
        'sql': "SELECT name, nationality, birth_date, field, genre FROM art"
    },
    
    # Join (3) - Note: These require multi-table joins, manual creation needed
    {
        'id': 'join_1',
        'type': 'join',
        'dataset': 'Med',
        'entity': 'disease,drug,institution',
        'requires_manual': True,
        'note': 'Three-way join across disease, drug, and institution tables'
    },
    {
        'id': 'join_2',
        'type': 'join',
        'dataset': 'Player',
        'entity': 'player,team,manager,city',
        'requires_manual': True,
        'note': 'Four-way join across player, team, manager, and city tables'
    },
    {
        'id': 'join_3',
        'type': 'join',
        'dataset': 'Med',
        'entity': 'disease,drug',
        'requires_manual': True,
        'note': 'Join disease and drug with complex filtering'
    },
    
    # Aggregation (3) - Note: These require GROUP BY calculations, manual creation needed
    {
        'id': 'agg_1',
        'type': 'aggregation',
        'dataset': 'Med',
        'entity': 'disease',
        'requires_manual': True,
        'note': 'GROUP BY disease_type with COUNT aggregation'
    },
    {
        'id': 'agg_2',
        'type': 'aggregation',
        'dataset': 'Finan',
        'entity': 'financial_record',
        'requires_manual': True,
        'note': 'GROUP BY principal_activities with AVG and SUM aggregations'
    },
    {
        'id': 'agg_3',
        'type': 'aggregation',
        'dataset': 'Player',
        'entity': 'player',
        'requires_manual': True,
        'note': 'GROUP BY position and nationality with COUNT and AVG aggregations'
    },
    
    # Union (3) - Note: These require UNION operations, manual creation needed
    {
        'id': 'union_1',
        'type': 'union',
        'dataset': 'Med',
        'entity': 'disease,drug',
        'requires_manual': True,
        'note': 'UNION of disease and drug tables'
    },
    {
        'id': 'union_2',
        'type': 'union',
        'dataset': 'Player',
        'entity': 'player',
        'requires_manual': True,
        'note': 'UNION of players with different filtering criteria'
    },
    {
        'id': 'union_3',
        'type': 'union',
        'dataset': 'Legal',
        'entity': 'legal_case',
        'requires_manual': True,
        'note': 'UNION of legal cases by verdict types'
    }
]

def apply_filter(df, where_clause):
    """Apply WHERE clause to dataframe."""
    result_df = df.copy()
    
    # Split by AND
    conditions = re.split(r'\s+AND\s+', where_clause, flags=re.IGNORECASE)
    
    for condition in conditions:
        condition = condition.strip()
        
        # Handle !=
        if '!=' in condition:
            col, val = condition.split('!=', 1)
            col = col.strip()
            val = val.strip().strip("'\"")
            if col in result_df.columns:
                result_df = result_df[result_df[col].astype(str) != val]
        
        # Handle >=
        elif '>=' in condition:
            col, val = condition.split('>=', 1)
            col = col.strip()
            val = val.strip().strip("'\"")
            if col in result_df.columns:
                try:
                    val_num = float(val)
                    result_df = result_df[pd.to_numeric(result_df[col], errors='coerce') >= val_num]
                except:
                    pass
        
        # Handle <=
        elif '<=' in condition:
            col, val = condition.split('<=', 1)
            col = col.strip()
            val = val.strip().strip("'\"")
            if col in result_df.columns:
                try:
                    val_num = float(val)
                    result_df = result_df[pd.to_numeric(result_df[col], errors='coerce') <= val_num]
                except:
                    pass
        
        # Handle >
        elif '>' in condition:
            col, val = condition.split('>', 1)
            col = col.strip()
            val = val.strip().strip("'\"")
            if col in result_df.columns:
                try:
                    val_num = float(val)
                    result_df = result_df[pd.to_numeric(result_df[col], errors='coerce') > val_num]
                except:
                    pass
        
        # Handle <
        elif '<' in condition:
            col, val = condition.split('<', 1)
            col = col.strip()
            val = val.strip().strip("'\"")
            if col in result_df.columns:
                try:
                    val_num = float(val)
                    result_df = result_df[pd.to_numeric(result_df[col], errors='coerce') < val_num]
                except:
                    pass
        
        # Handle =
        elif '=' in condition:
            col, val = condition.split('=', 1)
            col = col.strip()
            val = val.strip().strip("'\"")
            if col in result_df.columns:
                result_df = result_df[result_df[col].astype(str) == val]
    
    return result_df

def main():
    # Create ground truth directory
    gt_dir = PROJECT_ROOT / 'ground_truth' / 'queries'
    gt_dir.mkdir(parents=True, exist_ok=True)
    
    print('='*100)
    print('GENERATING GROUND TRUTH CSV FILES FOR ALL 17 CHALLENGING QUERIES')
    print('Independent of any specific run_id - TRUTH is determined by executing SQL on raw data')
    print('='*100)
    print()
    
    results_summary = []
    
    for query in QUERIES:
        query_id = query['id']
        qtype = query['type']
        dataset = query['dataset']
        entity = query['entity']
        
        print(f'{query_id:15s} ({qtype:12s}): ', end='')
        
        # Handle queries that require manual creation
        if query.get('requires_manual'):
            print(f'⚠️  MANUAL - {query.get("note", "")}')
            results_summary.append({
                'query_id': query_id,
                'type': qtype,
                'status': 'requires_manual',
                'note': query.get('note', '')
            })
            continue
        
        # For standard queries, execute against raw data
        entities = [e.strip() for e in entity.split(',')]
        if len(entities) > 1:
            print(f'⚠️  MULTI-ENTITY - Requires JOIN')
            results_summary.append({
                'query_id': query_id,
                'type': qtype,
                'status': 'multi_entity'
            })
            continue
        
        entity_name = entities[0]
        
        if dataset not in RAW_DATA or entity_name not in RAW_DATA[dataset]:
            print(f'⚠️  NO DATA PATH')
            results_summary.append({
                'query_id': query_id,
                'type': qtype,
                'status': 'no_data_path'
            })
            continue
        
        data_path = PROJECT_ROOT / RAW_DATA[dataset][entity_name]
        if not data_path.exists():
            print(f'⚠️  FILE NOT FOUND: {data_path}')
            results_summary.append({
                'query_id': query_id,
                'type': qtype,
                'status': 'file_not_found'
            })
            continue
        
        try:
            # Load raw data
            df = pd.read_csv(data_path)
            
            # Parse SQL
            sql = query['sql']
            select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
            if not select_match:
                print(f'❌ PARSE ERROR')
                continue
            
            select_cols_str = select_match.group(1).strip()
            select_cols = [c.strip() for c in select_cols_str.split(',')]
            
            # Apply WHERE if present
            result_df = df.copy()
            where_match = re.search(r'WHERE\s+(.*?)(?:GROUP BY|ORDER BY|LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
            
            if where_match:
                where_clause = where_match.group(1).strip()
                result_df = apply_filter(result_df, where_clause)
            
            # Select columns (case-insensitive)
            final_cols = []
            for sel_col in select_cols:
                for df_col in result_df.columns:
                    if df_col.lower() == sel_col.lower():
                        final_cols.append(df_col)
                        break
            
            if final_cols:
                result_df = result_df[final_cols].copy()
            
            # Save
            gt_file = gt_dir / f'{query_id}.csv'
            result_df.to_csv(gt_file, index=False)
            print(f'✓ {len(result_df):6d} rows -> {gt_file.name}')
            
            results_summary.append({
                'query_id': query_id,
                'type': qtype,
                'status': 'success',
                'rows': len(result_df)
            })
            
        except Exception as e:
            print(f'❌ ERROR: {str(e)[:50]}')
            results_summary.append({
                'query_id': query_id,
                'type': qtype,
                'status': 'error',
                'error': str(e)
            })
    
    # Summary
    print()
    print('='*100)
    print('SUMMARY:')
    print('-'*100)
    
    success = len([r for r in results_summary if r['status'] == 'success'])
    manual = len([r for r in results_summary if r['status'] == 'requires_manual'])
    
    print(f'Successfully generated: {success}/17')
    print(f'Requires manual creation: {manual}/17')
    print(f'Other: {17 - success - manual}/17')
    print()
    print(f'Ground truth files saved to: {gt_dir}')
    print('='*100)

if __name__ == '__main__':
    main()


