import argparse
import gc
import json
import platform
from datetime import datetime, timezone

import cupy as cp
import rmm
import torch

parser = argparse.ArgumentParser()
parser.add_argument('--mode', choices=['default', 'rmm'], required=True)
parser.add_argument('--scenario', choices=['reuse', 'release'], required=True)
parser.add_argument('--trial', type=int, required=True)
args = parser.parse_args()

MIB = 1024 * 1024

if args.mode == 'rmm':
    from rmm.allocators.cupy import rmm_cupy_allocator
    from rmm.allocators.torch import rmm_torch_allocator

    pool = rmm.mr.CudaAsyncMemoryResource(
        initial_pool_size=0, release_threshold=1024 * MIB
    )
    stats = rmm.mr.StatisticsResourceAdaptor(pool)
    rmm.mr.set_current_device_resource(stats)
    torch.cuda.memory.change_current_allocator(rmm_torch_allocator)
    cp.cuda.set_allocator(rmm_cupy_allocator)

torch.cuda.init()
cp.cuda.runtime.memGetInfo()
torch.cuda.synchronize()

result = {
    'utc': datetime.now(timezone.utc).isoformat(),
    'mode': args.mode,
    'scenario': args.scenario,
    'trial': args.trial,
    'gpu': torch.cuda.get_device_name(),
    'python': platform.python_version(),
    'torch': torch.__version__,
    'cupy': cp.__version__,
    'rmm': rmm.__version__,
    'cuda_runtime': cp.cuda.runtime.runtimeGetVersion(),
    'cuda_driver': cp.cuda.runtime.driverGetVersion(),
    'allocation_mib': 512 if args.scenario == 'reuse' else 2048,
    'release_threshold_mib': 1024,
    'samples': [],
}


def snapshot(stage):
    free, total = cp.cuda.runtime.memGetInfo()
    sample = {
        'stage': stage,
        'driver_free_mib': free / MIB,
        'driver_total_mib': total / MIB,
        'cupy_default_used_mib': cp.get_default_memory_pool().used_bytes() / MIB,
        'cupy_default_total_mib': cp.get_default_memory_pool().total_bytes() / MIB,
    }
    if args.mode == 'rmm':
        sample['rmm_live_mib'] = stats.allocation_counts.current_bytes / MIB
        sample['rmm_peak_mib'] = stats.allocation_counts.peak_bytes / MIB
    else:
        sample['torch_allocated_mib'] = torch.cuda.memory_allocated() / MIB
        sample['torch_reserved_mib'] = torch.cuda.memory_reserved() / MIB
    result['samples'].append(sample)


snapshot('baseline')
tensor = torch.empty(result['allocation_mib'] * MIB, dtype=torch.uint8, device='cuda')
snapshot('torch_allocated')
del tensor
gc.collect()
snapshot('torch_deleted')

if args.scenario == 'reuse':
    array = cp.empty(512 * MIB, dtype=cp.uint8)
    snapshot('cupy_allocated')
    del array
    gc.collect()
    snapshot('cupy_deleted')
    cp.get_default_memory_pool().free_all_blocks()
    snapshot('cupy_free_all_blocks')
else:
    torch.cuda.synchronize()
    snapshot('synchronized')
    torch.cuda.empty_cache()
    snapshot('torch_empty_cache')

try:
    result['torch_counter_result'] = {
        'allocated_mib': torch.cuda.memory_allocated() / MIB,
        'reserved_mib': torch.cuda.memory_reserved() / MIB,
    }
except RuntimeError as error:
    if 'getDeviceStats' not in str(error):
        raise
    result['torch_counter_result'] = str(error)

print(json.dumps(result, ensure_ascii=False), flush=True)
