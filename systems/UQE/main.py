import argparse
import sys

# 导入各个模块的main函数
from main_Art import main as main_art
from main_Art_image import main as main_art_image
from main_disease import main as main_disease
from main_disease_optimized import main as main_disease_optimized
from main_drug import main as main_drug
from main_fin import main as main_fin
from main_institutes import main as main_institutes
from main_LCR import main as main_lcr
from main_player import main as main_player
from main_player_optimized import main as main_player_optimized

# 导入配置
import config_uqe


class UQEMain:
    
    def __init__(self):
        self.dataset_handlers = {
            'art': main_art,
            'art_image': main_art_image,
            'disease': main_disease,
            'drug': main_drug,
            'finance': main_fin,
            'institutes': main_institutes,
            'lcr': main_lcr,
            'player': main_player
        }
        
        # Optimized handlers (if available)
        self.optimized_handlers = {
            'disease': main_disease_optimized,
            'player': main_player_optimized,
        }
    
    def print_config(self):
        """Print current configuration"""
        print("=" * 50)
        print("UQE Configuration:")
        print("=" * 50)
        print(f"USE_BART: {config_uqe.USE_BART}")
        print(f"BATCH_SIZE: {config_uqe.BATCH_SIZE}")
        print(f"BUDGET: {config_uqe.BUDGET}")
        print(f"AGGR_STRATEGY: {config_uqe.AGGR_STRATEGY}")
        print(f"N_CENTROIDS: {config_uqe.N_CENTROIDS}")
        print(f"N_ITER: {config_uqe.N_ITER}")
        print(f"GROUP_EXTRACT_SAMPLE_RATIO: {config_uqe.GROUP_EXTRACT_SAMPLE_RATIO}")
        print(f"AGGR_CLUSTER_SAMPLE_RATIO: {config_uqe.AGGR_CLUSTER_SAMPLE_RATIO}")
        print("=" * 50)
        print("UQE Optimizations:")
        print("=" * 50)
        print(f"ENABLE_OPTIMIZATIONS: {config_uqe.ENABLE_OPTIMIZATIONS}")
        print(f"ENABLE_STRATIFIED_SAMPLING: {config_uqe.ENABLE_STRATIFIED_SAMPLING}")
        print(f"ENABLE_ACTIVE_LEARNING: {config_uqe.ENABLE_ACTIVE_LEARNING}")
        print(f"ENABLE_QUERY_OPTIMIZATION: {config_uqe.ENABLE_QUERY_OPTIMIZATION}")
        print("=" * 50)
    
    def run_single_dataset(self, dataset_name: str, query_type: str = None, use_optimizations: bool = None):
        """Run single dataset with optional optimizations"""
        if dataset_name not in self.dataset_handlers:
            print(f"Error: Dataset '{dataset_name}' not found!")
            return False

        print(f"Running dataset: {dataset_name}")
        
        # Determine if optimizations should be used
        use_opts = config_uqe.ENABLE_OPTIMIZATIONS if use_optimizations is None else use_optimizations
        
        try:
            # Use optimized handler if available and enabled
            if use_opts and dataset_name in self.optimized_handlers:
                print(f"Using OPTIMIZED execution for {dataset_name}")
                self.optimized_handlers[dataset_name](query_type, use_optimizations=True)
            else:
                # Use standard handler
                if use_opts:
                    print(f"Optimizations not available for {dataset_name}, using standard execution")
                self.dataset_handlers[dataset_name](query_type)
            
            print(f"Successfully completed dataset: {dataset_name}")
            return True
            
        except Exception as e:
            print(f"Error running dataset {dataset_name}: {str(e)}")
            return False
    
    def run_all_datasets(self, query_type: str = None, use_optimizations: bool = None):
        """Run all datasets with optional optimizations"""
        use_opts = config_uqe.ENABLE_OPTIMIZATIONS if use_optimizations is None else use_optimizations
        opt_mode = "WITH OPTIMIZATIONS" if use_opts else "BASELINE"
        print(f"Running all datasets ({opt_mode})...")
        self.print_config()
        
        results = {}
        for dataset_name in self.dataset_handlers.keys():
            print(f"\n{'='*20} Processing {dataset_name} {'='*20}")
            success = self.run_single_dataset(dataset_name, query_type, use_optimizations=use_opts)
            results[dataset_name] = success
        
        # Print execution summary
        print("\n" + "="*50)
        print("Execution Summary:")
        print("="*50)
        for dataset, success in results.items():
            status = "✓ SUCCESS" if success else "✗ FAILED"
            print(f"{dataset}: {status}")
        
        successful = sum(results.values())
        total = len(results)
        print(f"\nTotal: {successful}/{total} datasets completed successfully")
        
        return results


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='UQE - Unified Query Execution')
    parser.add_argument('--dataset', '-d', type=str, 
                       help='Dataset to run (art, art_image, disease, drug, finance, institutes, lcr, player)')
    parser.add_argument('--all', '-a', action='store_true',
                       help='Run all datasets')
    parser.add_argument('--query-type', '-q', type=str,
                       help='Override query type for all datasets')
    parser.add_argument('--optimize', '-o', action='store_true',
                       help='Enable UQE optimizations (stratified sampling, active learning, query optimization)')
    parser.add_argument('--baseline', '-b', action='store_true',
                       help='Run without optimizations (baseline)')
    
    args = parser.parse_args()
    
    uqe = UQEMain()

    uqe.print_config()
    
    # Determine optimization setting
    use_optimizations = None  # Will use config default
    if args.optimize:
        use_optimizations = True
    elif args.baseline:
        use_optimizations = False
    
    # 运行单个数据集
    if args.dataset:
        success = uqe.run_single_dataset(args.dataset, args.query_type, 
                                         use_optimizations=use_optimizations)
        sys.exit(0 if success else 1)
    
    # 运行所有数据集
    if args.all:
        results = uqe.run_all_datasets(args.query_type, 
                                       use_optimizations=use_optimizations)
        all_success = all(results.values())
        sys.exit(0 if all_success else 1)
    
    # If no arguments specified, show help
    if not any([args.dataset, args.all]):
        parser.print_help()
        print("\nExamples:")
        print("  python main.py --dataset disease                    # Run disease dataset (uses config)")
        print("  python main.py --dataset disease --optimize         # Run disease with optimizations")
        print("  python main.py --dataset disease --baseline         # Run disease without optimizations")
        print("  python main.py --dataset disease --query-type SFW   # Run disease with SFW queries")
        print("  python main.py --all --optimize                     # Run all datasets with optimizations")
        print("  python main.py --all --baseline                     # Run all datasets without optimizations")


if __name__ == '__main__':
    main() 