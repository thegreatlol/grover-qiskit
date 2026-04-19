from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit_aer import AerSimulator
from qiskit.visualization import plot_histogram
from qiskit_aer.noise import NoiseModel, depolarizing_error
import matplotlib.pyplot as plt
import numpy as np


def build_noise_model(p1, p2):
    """
    Builds a depolarizing noise model simulating realistic hardware error rates.
    p1: error probability for single-qubit gates (H, X) — typically ~1% on IBM hardware
    p2: error probability for multi-qubit gates (CX, CCX) — typically ~5%, the dominant bottleneck
    """
    noise_model = NoiseModel()
    error_1q = depolarizing_error(p1, 1)  # single-qubit depolarizing channel
    error_2q = depolarizing_error(p2, 2)  # two-qubit depolarizing channel
    error_3q = depolarizing_error(p2, 3)  # three-qubit depolarizing channel (CCX)
    noise_model.add_all_qubit_quantum_error(error_1q, ['h', 'x'])
    noise_model.add_all_qubit_quantum_error(error_2q, ['cx'])
    noise_model.add_all_qubit_quantum_error(error_3q, ['ccx'])
    return noise_model


def build_oracle(qc, qr, target):
    """
    Parameterized phase-kickback oracle. Marks the target state by flipping its
    amplitude from +1 to -1 without collapsing superposition.

    For each qubit where target has '0', we apply X to flip it so the MCX fires
    correctly, then unflip afterward. The H-MCX-H sandwich on the last qubit
    implements the phase kickback — converting a bit flip into a phase flip.

    Works for any n-bit target string without modifying circuit logic.
    """
    # flip qubits where target is '0' so MCX condition fires on target state
    for i, bit in enumerate(reversed(target)):
        if bit == '0':
            qc.x(qr[i])

    # phase kickback: H-MCX-H flips phase of |target> from +1 to -1
    qc.h(qr[-1])
    qc.mcx(list(range(len(qr)-1)), len(qr)-1)  # multi-controlled X on last qubit
    qc.h(qr[-1])

    # unflip qubits to restore register state
    for i, bit in enumerate(reversed(target)):
        if bit == '0':
            qc.x(qr[i])


def build_diffusion(qc, qr):
    """
    Grover diffusion operator — reflects all amplitudes around their mean.
    Also called the inversion-about-average operator.

    After the oracle tags the target with a negative amplitude, the target sits
    below the mean. Reflection pushes it above the mean and suppresses all others.
    Repeating oracle + diffusion k = (pi/4)*sqrt(N) times maximizes success probability.
    """
    # rotate into Hadamard basis
    for i in range(len(qr)):
        qc.h(qr[i])

    # flip all qubits to isolate |000...0> state
    for i in range(len(qr)):
        qc.x(qr[i])

    # phase kickback on |000...0>
    qc.h(qr[-1])
    qc.mcx(list(range(len(qr)-1)), len(qr)-1)
    qc.h(qr[-1])

    # unflip
    for i in range(len(qr)):
        qc.x(qr[i])

    # rotate back to computational basis
    for i in range(len(qr)):
        qc.h(qr[i])


def scaling_analysis(target_template, max_n=5, iterations=2, shots=1024):
    """
    Benchmarks Grover's performance across qubit counts n=2 to max_n.
    Fixes iteration count at 2 to show how performance degrades when
    iterations deviate from the theoretical optimal k = (pi/4)*sqrt(2^n).

    Produces two plots:
    - Success probability vs n for ideal and noisy simulators
    - Optimal vs actual iteration count vs n
    """
    ns = list(range(2, max_n + 1))
    ideal_probs = []
    noisy_probs = []

    for n in ns:
        # generate valid n-bit target from template, padding with 0s if needed
        target = target_template[:n].ljust(n, '0')

        def run(noise_model=None):
            # closure captures current n and target from outer loop
            qr = QuantumRegister(n, name='q')
            cr = ClassicalRegister(n, name='c')
            qc = QuantumCircuit(qr, cr)

            # initialize uniform superposition over all 2^n states
            for i in range(n):
                qc.h(qr[i])

            # alternate oracle and diffusion for k iterations
            for _ in range(iterations):
                qc.barrier()
                build_oracle(qc, qr, target)
                qc.barrier()
                build_diffusion(qc, qr)
                qc.barrier()

            qc.measure(qr, cr)
            simulator = AerSimulator()
            job = simulator.run(qc, shots=shots, noise_model=noise_model)
            return job.result().get_counts()

        ideal_counts = run()
        noisy_counts = run(build_noise_model(0.01, 0.05))

        # convert raw counts to probabilities
        ideal_probs.append(ideal_counts.get(target, 0) / shots)
        noisy_probs.append(noisy_counts.get(target, 0) / shots)
        print(f"n={n}, target={target}, ideal={ideal_probs[-1]:.3f}, noisy={noisy_probs[-1]:.3f}")

    # theoretical optimal iteration count per qubit count
    optimal_iters = [(np.pi / 4) * np.sqrt(2**n) for n in ns]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    ax1.plot(ns, ideal_probs, 'b-o', label='Ideal')
    ax1.plot(ns, noisy_probs, 'r-o', label='Noisy')
    ax1.set_xlabel('Number of Qubits (n)')
    ax1.set_ylabel('Success Probability')
    ax1.set_title('Success Probability vs Qubits (fixed 2 iterations)')
    ax1.legend()
    ax1.grid(True)

    ax2.plot(ns, [2] * len(ns), 'g--', label='Actual iterations (2)')
    ax2.plot(ns, optimal_iters, 'b-o', label='Optimal iterations')
    ax2.set_xlabel('Number of Qubits (n)')
    ax2.set_ylabel('Iterations')
    ax2.set_title('Optimal vs Actual Iterations')
    ax2.legend()
    ax2.grid(True)

    plt.tight_layout()
    plt.savefig('grover_scaling.png')
    print("Scaling plot saved to grover_scaling.png")


if __name__ == "__main__":
    n = 3
    target = '101'  # change this to any n-bit binary string
    iterations = 2  # optimal for n=3: (pi/4)*sqrt(8) ≈ 2.2

    def run_grover(noise_model=None):
        qr = QuantumRegister(n, name='q')
        cr = ClassicalRegister(n, name='c')
        qc = QuantumCircuit(qr, cr)

        # superposition: all 2^n states with equal amplitude 1/sqrt(2^n)
        for i in range(n):
            qc.h(qr[i])

        # amplitude amplification: k iterations of oracle + diffusion
        for _ in range(iterations):
            qc.barrier()
            build_oracle(qc, qr, target)
            qc.barrier()
            build_diffusion(qc, qr)
            qc.barrier()

        qc.measure(qr, cr)

        simulator = AerSimulator()
        job = simulator.run(qc, shots=1024, noise_model=noise_model)
        result = job.result()
        return result.get_counts()

    counts_ideal = run_grover()
    counts_noisy = run_grover(build_noise_model(p1=0.01, p2=0.05))

    print("Ideal:", counts_ideal)
    print("Noisy:", counts_noisy)

    plot_histogram([counts_ideal, counts_noisy],
                   legend=['Ideal', 'Noisy'],
                   title="Grover's Algorithm: Ideal vs Noisy"
                   ).savefig('grover_results.png')

    scaling_analysis('101')