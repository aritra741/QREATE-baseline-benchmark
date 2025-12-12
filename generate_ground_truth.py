#!/usr/bin/env python3
"""
Generate ground truth CSV files for all 17 challenging queries.
"""

import pandas as pd
import json
from pathlib import Path
import re

PROJECT_ROOT = Path('.')
RUN_ID = '20251211_000936'

# Correct ground truth data paths
GT_DATA = {
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

def apply_filter(df, where_clause):
    """Apply WHERE clause to dataframe."""
    result_df = df.copy()
    
    # Split by AND (simple parser - doesn't handle OR or parentheses)
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
    # Load detailed report
    with open(PROJECT_ROOT / 'results' / 'challenging_queries' / RUN_ID / 'detailed_report.json') as f:
        report = json.load(f)
    
    # Create ground truth directory
    gt_dir = PROJECT_ROOT / 'ground_truth' / 'challenging_queries'
    gt_dir.mkdir(parents=True, exist_ok=True)
    
    # Also create a notes file
    notes_file = gt_dir / 'README.md'
    notes = []
    notes.append('# Ground Truth Files for Challenging Queries\n\n')
    
    print('='*100)
    print('GENERATING GROUND TRUTH CSV FILES FOR ALL 17 QUERIES')
    print('='*100)
    print()
    
    results_summary = []
    
    for query_id in sorted(report['systems']['uqe']['queries'].keys()):
        query_data = report['systems']['uqe']['queries'][query_id]
        qtype = query_data['query_type']
        
        # Load query info
        query_path = PROJECT_ROOT / 'results' / 'challenging_queries' / RUN_ID / 'results' / 'uqe' / qtype / query_id / 'query.json'
        
        if not query_path.exists():
            print(f'⚠️  {query_id}: Query file not found')
            continue
        
        with open(query_path) as f:
            query_info = json.load(f)
        
        dataset = query_info.get('dataset')
        entity = query_info.get('entity')
        sql = query_info.get('sql', '')
        
        print(f'{query_id} ({qtype}): {query_info.get("name", "")}')
        
        # Handle different query types
        if qtype == 'join':
            print(f'  ⚠️  JOIN query - requires manual creation')
            notes.append(f'## {query_id}\n- Type: JOIN\n- Status: Requires manual creation (multi-table)\n\n')
            results_summary.append({'query_id': query_id, 'status': 'join_manual'})
        
        elif qtype == 'union':
            print(f'  ⚠️  UNION query - requires manual creation')
            notes.append(f'## {query_id}\n- Type: UNION\n- Status: Requires manual creation\n\n')
            results_summary.append({'query_id': query_id, 'status': 'union_manual'})
        
        elif qtype == 'aggregation':
            # Try to calculate aggregations
            print(f'  ⚠️  AGGREGATION query - calculating manually')
            
            # Parse GROUP BY and aggregation functions
            if dataset in GT_DATA and entity in GT_DATA[dataset]:
                gt_path = PROJECT_ROOT / GT_DATA[dataset][entity]
                if gt_path.exists():
                    df = pd.read_csv(gt_path)
                    
                    # Extract aggregation details from SQL
                    # For now, mark as manual
                    print(f'    Data loaded ({len(df)} rows), but aggregation logic needs manual implementation')
                    notes.append(f'## {query_id}\n- Type: AGGREGATION\n- Status: Requires manual calculation\n- SQL: `{sql[:100]}...`\n\n')
                    results_summary.append({'query_id': query_id, 'status': 'aggregation_manual'})
            
        else:
            # Handle simple, filter, projection
            entities = [e.strip() for e in entity.split(',')]
            if len(entities) > 1:
                print(f'  ⚠️  Multi-entity query')
                notes.append(f'## {query_id}\n- Type: {qtype.upper()}\n- Status: Multi-entity - requires JOIN\n\n')
                results_summary.append({'query_id': query_id, 'status': 'multi_entity'})
                continue
            
            entity_name = entities[0]
            
            if dataset not in GT_DATA or entity_name not in GT_DATA[dataset]:
                print(f'  ⚠️  No data path for {dataset}/{entity_name}')
                notes.append(f'## {query_id}\n- Type: {qtype.upper()}\n- Status: No data path defined\n\n')
                results_summary.append({'query_id': query_id, 'status': 'no_data'})
                continue
            
            gt_path = PROJECT_ROOT / GT_DATA[dataset][entity_name]
            if not gt_path.exists():
                print(f'  ⚠️  File not found: {gt_path}')
                notes.append(f'## {query_id}\n- Type: {qtype.upper()}\n- Status: Data file not found\n\n')
                results_summary.append({'query_id': query_id, 'status': 'file_not_found'})
                continue
            
            try:
                # Load data
                df = pd.read_csv(gt_path)
                print(f'  ✓ Loaded {len(df)} rows')
                
                # Parse SQL
                select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
                if not select_match:
                    print(f'  ⚠️  Could not parse SELECT')
                    continue
                
                select_cols_str = select_match.group(1).strip()
                select_cols = [c.strip() for c in select_cols_str.split(',')]
                
                # Apply WHERE if present
                result_df = df.copy()
                where_match = re.search(r'WHERE\s+(.*?)(?:GROUP BY|ORDER BY|LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
                
                if where_match:
                    where_clause = where_match.group(1).strip()
                    print(f'  Applying WHERE...')
                    result_df = apply_filter(result_df, where_clause)
                
                # Select columns (case-insensitive)
                final_cols = []
                virtual_cols = []
                
                for sel_col in select_cols:
                    found = False
                    for df_col in result_df.columns:
                        if df_col.lower() == sel_col.lower():
                            final_cols.append(df_col)
                            found = True
                            break
                    if not found:
                        virtual_cols.append(sel_col)
                
                if virtual_cols:
                    print(f'  ⚠️  Virtual columns (not in raw data): {virtual_cols}')
                    notes.append(f'## {query_id}\n- Type: {qtype.upper()}\n- Status: Contains virtual columns: {virtual_cols}\n- Note: Ground truth only includes physical columns\n\n')
                
                if final_cols:
                    result_df = result_df[final_cols].copy()
                
                # Save
                gt_file = gt_dir / f'{query_id}_ground_truth.csv'
                result_df.to_csv(gt_file, index=False)
                print(f'  ✓ Saved: {len(result_df)} rows -> {gt_file.name}')
                
                results_summary.append({
                    'query_id': query_id,
                    'status': 'success',
                    'rows': len(result_df),
                    'has_virtual_cols': len(virtual_cols) > 0
                })
                
                if not virtual_cols:
                    notes.append(f'## {query_id}\n- Type: {qtype.upper()}\n- Status: ✓ Complete\n- Rows: {len(result_df)}\n\n')
                
            except Exception as e:
                print(f'  ❌ Error: {str(e)}')
                notes.append(f'## {query_id}\n- Type: {qtype.upper()}\n- Status: Error - {str(e)}\n\n')
                results_summary.append({'query_id': query_id, 'status': 'error', 'error': str(e)})
        
        print()
    
    # Write notes
    with open(notes_file, 'w') as f:
        f.write(''.join(notes))
    
    # Summary
    print('='*100)
    print('SUMMARY:')
    print('-'*100)
    
    success = len([r for r in results_summary if r.get('status') == 'success'])
    with_virtual = len([r for r in results_summary if r.get('status') == 'success' and r.get('has_virtual_cols')])
    
    print(f'Successfully generated: {success}/17 ground truth files')
    print(f'  - Complete (no virtual columns): {success - with_virtual}')
    print(f'  - Partial (has virtual columns): {with_virtual}')
    print(f'  - Requires manual creation: {17 - success}')
    print(f'\nFiles saved to: {gt_dir}')
    print(f'Notes saved to: {notes_file}')
    print('='*100)

if __name__ == '__main__':
    main()

