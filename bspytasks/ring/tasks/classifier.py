import os
import torch
import numpy as np
import matplotlib.pyplot as plt

from bspytasks.ring.data import RingDatasetGenerator, RingDatasetLoader

from bspyalgo.algorithms.gradient.fitter import train, split
from bspyalgo.manager import get_criterion, get_optimizer
from bspyalgo.utils.io import save
from bspyproc.utils.pytorch import TorchUtils
from bspyalgo.utils.io import create_directory, create_directory_timestamp, save
from bspyalgo.utils.performance import perceptron, corr_coeff_torch, plot_perceptron


def ring_task(dataloaders, custom_model, configs, transforms=None, logger=None, is_main=True):
    results = {}
    results['gap'] = str(dataloaders[0].dataset.gap)
    main_dir, results_dir, reproducibility_dir = init_dirs(str(dataloaders[0].dataset.gap), configs['results_base_dir'], is_main)
    criterion = get_criterion(configs['algorithm'])
    print('==========================================================================================')
    print("GAP: " + str(dataloaders[0].dataset.gap))
    model = custom_model(configs['processor'])
    optimizer = get_optimizer(filter(lambda p: p.requires_grad, model.parameters()), configs['algorithm'])

    model, performances = train(model, (dataloaders[0], dataloaders[1]), configs['algorithm']['epochs'], criterion, optimizer, logger=logger, save_dir=reproducibility_dir)

    if len(dataloaders[0]) > 0:
        results['train_results'] = postprocess(dataloaders[0].dataset[dataloaders[0].sampler.indices], model, criterion, logger, main_dir)
        results['train_results']['performance_history'] = performances[0]
    if len(dataloaders[1]) > 0:
        results['dev_results'] = postprocess(dataloaders[1].dataset[dataloaders[1].sampler.indices], model, criterion, logger, main_dir)
        results['dev_results']['performance_history'] = performances[1]
    if len(dataloaders[2]) > 0:
        results['test_results'] = postprocess(dataloaders[2].dataset[dataloaders[2].sampler.indices], model, criterion, logger, main_dir)
    plot_results(results, plots_dir=results_dir)
    torch.save(results, os.path.join(reproducibility_dir, 'results.pickle'))
    save('configs', os.path.join(reproducibility_dir, 'configs.yaml'), data=configs)
    print('==========================================================================================')
    return results


def get_ring_data(gap, configs, transforms, data_dir=None):
    # Returns dataloaders and split indices
    if configs['data']['load']:
        dataset = RingDatasetLoader(data_dir, transforms=transforms, save_dir=data_dir)
    else:
        dataset = RingDatasetGenerator(configs['data']['sample_no'], gap, transforms=transforms, save_dir=data_dir)
    dataloaders = split(dataset, configs['algorithm']['batch_size'], num_workers=configs['algorithm']['worker_no'], split_percentages=configs['data']['split_percentages'])
    return dataloaders


def postprocess(dataset, model, criterion, logger, save_dir=None):
    results = {}
    with torch.no_grad():
        model.eval()
        inputs, targets = dataset[:]
        indices = torch.argsort(targets[:, 0], dim=0)
        inputs, targets = inputs[indices], targets[indices]
        predictions = model(inputs)
        results['performance'] = criterion(predictions, targets)

    #results['gap'] = dataset.gap
    results['inputs'] = inputs
    results['targets'] = targets
    results['best_output'] = predictions
    results['accuracy'] = perceptron(predictions, targets)  # accuracy(predictions.squeeze(), targets.squeeze(), plot=None, return_node=True)
    results['correlation'] = corr_coeff_torch(predictions.T, targets.T)

    return results


def init_dirs(gap, base_dir, is_main=False):
    base_dir = os.path.join(base_dir, 'gap_' + gap)
    main_dir = 'ring_classification'
    reproducibility_dir = 'reproducibility'
    results_dir = 'results'
    if is_main:
        base_dir = create_directory_timestamp(base_dir, main_dir)
    reproducibility_dir = os.path.join(base_dir, reproducibility_dir)
    create_directory(reproducibility_dir)
    results_dir = os.path.join(base_dir, results_dir)
    create_directory(results_dir)
    return main_dir, results_dir, reproducibility_dir


def plot_results(results, plots_dir=None, show_plots=False, extension='png'):
    plot_output(results['train_results'], 'Train', plots_dir=plots_dir, extension=extension)
    if 'dev_results' in results:
        plot_output(results['dev_results'], 'Dev', plots_dir=plots_dir, extension=extension)
    if 'test_results' in results:
        plot_output(results['test_results'], 'Test', plots_dir=plots_dir, extension=extension)
    plt.figure()
    plt.title(f'Learning profile', fontsize=12)
    plt.plot(TorchUtils.get_numpy_from_tensor(results['train_results']['performance_history']), label='Train')
    if 'dev_results' in results:
        plt.plot(TorchUtils.get_numpy_from_tensor(results['dev_results']['performance_history']), label='Dev')
    plt.legend()
    if plots_dir is not None:
        plt.savefig(os.path.join(plots_dir, f"training_profile." + extension))

    plt.figure()
    plt.title(f"Inputs (V) \n {results['gap']} gap (-1 to 1 scale)", fontsize=12)
    plot_inputs(results['train_results'], 'Train', ['blue', 'cornflowerblue'])
    if 'dev_results' in results:
        plot_inputs(results['dev_results'], 'Dev', ['orange', 'bisque'])
    if 'test_results' in results:
        plot_inputs(results['test_results'], 'Test', ['green', 'springgreen'])
    plt.legend()
    # if type(results['dev_inputs']) is torch.Tensor:
    if plots_dir is not None:
        plt.savefig(os.path.join(plots_dir, f"input." + extension))

    if show_plots:
        plt.show()
    plt.close('all')


def plot_output(results, label, plots_dir=None, extension='png'):
    plt.figure()
    plt.plot(results['best_output'].detach().cpu())
    plt.title(f"{label} Output (nA) \n Performance: {results['performance']} \n Accuracy: {results['accuracy']['accuracy_value']}", fontsize=12)
    if plots_dir is not None:
        plt.savefig(os.path.join(plots_dir, label + "_output." + extension))


def plot_inputs(results, label, colors=['b', 'r'], plots_dir=None, extension='png'):
    # if type(results['dev_inputs']) is torch.Tensor:
    inputs = results['inputs'].cpu().numpy()
    targets = results['targets'][:, 0].cpu().numpy()
    # else:
    #     inputs = results['dev_inputs']
    #     targets = results['dev_targets']
    plt.scatter(inputs[targets == 0][:, 0], inputs[targets == 0][:, 1], c=colors[0], label='Class 0 (' + label + ')', cmap=colors)
    plt.scatter(inputs[targets == 1][:, 0], inputs[targets == 1][:, 1], c=colors[1], label='Class 1 (' + label + ')', cmap=colors)


if __name__ == '__main__':
    from torchvision import transforms

    from bspyalgo.utils.io import load_configs
    from bspyalgo.utils.transforms import ToTensor, ToVoltageRange
    from bspyproc.processors.dnpu import DNPU

    V_MIN = [-1.2, -1.2]
    V_MAX = [0.7, 0.7]

    transforms = transforms.Compose([
        ToVoltageRange(V_MIN, V_MAX, -1, 1),
        ToTensor()
    ])

    gap = 0.4
    configs = load_configs('configs/ring.yaml')
    dataloaders = get_ring_data(gap, configs, transforms)

    ring_task(dataloaders, DNPU, configs)