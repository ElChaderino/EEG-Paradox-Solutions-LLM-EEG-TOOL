# EEG Fundamentals Reference

## What is EEG?

Electroencephalography (EEG) records the electrical activity of the brain via electrodes placed on the scalp. It measures voltage fluctuations resulting from ionic current flows within neurons, primarily postsynaptic potentials of cortical pyramidal cells. EEG has millisecond temporal resolution, making it ideal for studying rapid neural dynamics.

## History

- **1875** — Richard Caton first recorded electrical activity from animal brains using a galvanometer.
- **1924** — Hans Berger recorded the first human EEG, identifying alpha rhythms (the "Berger rhythm").
- **1934** — Adrian and Matthews confirmed Berger's findings, establishing EEG as a legitimate tool.
- **1937** — Gibbs, Davis, and Lennox described EEG patterns in epilepsy.
- **1958** — The International 10-20 system was standardized for electrode placement.
- **1970s** — Quantitative EEG (QEEG) emerged with computer-based spectral analysis.
- **1990s** — Independent Component Analysis (ICA) revolutionized artifact removal.
- **2000s** — Source localization (sLORETA, eLORETA) matured; high-density EEG became practical.
- **2010s** — Real-time neurofeedback went mainstream; open-source tools (MNE-Python, OpenBCI) democratized research.

## Frequency Bands

| Band | Frequency | Amplitude | Brain state / function |
|------|-----------|-----------|----------------------|
| Delta | 0.5 -- 4 Hz | 20-200 uV | Deep sleep (stages 3-4), healing, cortical inhibition; excess in waking = pathology |
| Theta | 4 -- 8 Hz | 5-100 uV | Drowsiness, light sleep, meditation, memory encoding (hippocampal theta), creative states |
| Alpha | 8 -- 13 Hz | 10-50 uV | Relaxed wakefulness, eyes closed; posterior dominant rhythm (PDR); attenuates with eyes open or mental effort |
| SMR (Mu) | 12 -- 15 Hz | 5-20 uV | Sensorimotor idle rhythm at central sites (C3/Cz/C4); suppressed by movement or motor imagery |
| Beta | 13 -- 30 Hz | 5-30 uV | Active cognition, alertness, concentration; subdivided into low-beta (13-16), mid-beta (16-20), hi-beta (20-30) |
| Hi-Beta | 20 -- 30 Hz | 2-20 uV | Hypervigilance, anxiety, rumination; excess correlates with generalized anxiety and OCD |
| Gamma | 30 -- 100+ Hz | 1-10 uV | Perceptual binding, higher cognitive functions, working memory; often 40 Hz peak; susceptible to muscle artifact |

## The 10-20 System

The International 10-20 system is the standard electrode placement method:

- **Letters**: Fp (frontopolar), F (frontal), C (central), T (temporal), P (parietal), O (occipital)
- **Numbers**: Odd = left hemisphere, Even = right hemisphere, z = midline
- **Key sites**: Fz (midline frontal), Cz (vertex), Pz (midline parietal), Oz (midline occipital)
- **21 electrodes** in standard 10-20; extended 10-10 system provides 64+ channels
- **Reference electrodes**: linked mastoids (A1/A2), average reference, Cz reference, or nose tip

## Common Artifacts

| Artifact | Source | Frequency range | Removal method |
|----------|--------|----------------|----------------|
| Eye blink | Orbicularis oculi | 0-5 Hz, frontal | ICA, regression, EOG channel |
| Saccade | Eye movement | 0-5 Hz, frontal/temporal | ICA |
| EMG (muscle) | Scalp muscles | 20-300 Hz, temporal/frontal | ICA, high-frequency filtering |
| ECG | Heart | ~1 Hz periodic | ICA, ECG channel template |
| 50/60 Hz line noise | Mains power | 50 or 60 Hz | Notch filter |
| Electrode pop | Poor contact | Broadband spike | Bad channel interpolation |
| Sweat / drift | Galvanic skin | < 0.5 Hz | High-pass filter (0.1 Hz) |

## Standard Preprocessing Pipeline

1. **Import** raw data (EDF, BDF, FIF, BrainVision, etc.)
2. **Inspect** channels, sampling rate, duration
3. **Set montage** (10-20 or custom electrode positions)
4. **Notch filter** at 50 Hz or 60 Hz (power line noise)
5. **Bandpass filter** 0.1 -- 100 Hz (or 0.5-45 Hz for clinical)
6. **Identify bad channels** (flat, noisy) and interpolate
7. **Re-reference** to average, linked mastoids, or REST
8. **ICA decomposition** (typically 15-25 components)
9. **Identify artifact components** (EOG, EMG, ECG) automatically or visually
10. **Remove artifact components** and reconstruct clean signal
11. **Epoch** around events (for ERP analysis) or segment into fixed windows
12. **Reject bad epochs** by amplitude threshold or autoreject
13. **Baseline correct** (subtract pre-stimulus mean)

## Key ERP Components

| Component | Latency | Polarity | Location | Paradigm | Cognitive function |
|-----------|---------|----------|----------|----------|-------------------|
| N100 (N1) | 80-120 ms | Negative | Central/frontal | Auditory/visual | Sensory processing, attention |
| P200 (P2) | 150-250 ms | Positive | Central | Auditory/visual | Feature detection, early classification |
| N170 | 130-200 ms | Negative | Occipitotemporal | Face perception | Face/object structural encoding |
| N200 (N2) | 200-350 ms | Negative | Frontal/central | Go/NoGo, flanker | Conflict monitoring, inhibition |
| P300 (P3) | 250-500 ms | Positive | Parietal (P3b), Frontal (P3a) | Oddball | Context updating (P3b), novelty (P3a) |
| N400 | 300-500 ms | Negative | Centroparietal | Semantic | Semantic integration difficulty |
| P600 | 500-800 ms | Positive | Centroparietal | Syntactic | Syntactic reanalysis, repair |
| MMN | 100-250 ms | Negative | Frontal/central | Oddball (passive) | Pre-attentive change detection |
| ERN | 0-100 ms post-response | Negative | Frontocentral | Error tasks | Error detection (ACC) |

## QEEG (Quantitative EEG)

QEEG involves converting raw EEG into numerical values for statistical comparison:

- **Absolute power**: total power in each band (uV^2) at each electrode
- **Relative power**: band power / total power (percentage)
- **Power ratios**: theta/beta ratio (attention), theta/alpha ratio (drowsiness)
- **Coherence**: frequency-domain correlation between electrode pairs (functional connectivity)
- **Phase**: phase relationships between channels (synchronization)
- **Asymmetry**: left vs. right hemisphere power differences (e.g., frontal alpha asymmetry in depression)
- **Z-scores**: individual values compared to age-matched normative databases

### Normative Databases
- **NeuroGuide** (Thatcher): largest lifespan database (2 months to 82 years), FDA-cleared
- **qEEG-Pro**: cloud-based normative comparison
- **BrainDx**: machine-learning enhanced QEEG
- **NYU/Hudspeth**: Nx-Link database

## Connectivity Measures

| Measure | Type | What it captures |
|---------|------|-----------------|
| Coherence | Linear, frequency-domain | Amplitude + phase coupling between channels |
| Phase-Lag Index (PLI) | Nonlinear | Phase coupling robust to volume conduction |
| Phase-Locking Value (PLV) | Nonlinear | Phase synchronization strength |
| Imaginary Coherence | Linear | Phase coupling (ignores zero-lag) |
| Granger Causality | Directed | Predictive influence A->B |
| DTF / PDC | Directed, multivariate | Directed transfer function / partial directed coherence |
| Mutual Information | Nonlinear | General statistical dependence |

## Source Localization

- **sLORETA** (standardized Low Resolution Electromagnetic Tomography): Pascual-Marqui, 2002. Zero localization error for single sources. Most widely used.
- **eLORETA** (exact LORETA): improved version with exact zero-error properties for any number of sources.
- **LORETA** (original): Pascual-Marqui, 1994. Lower resolution than sLORETA.
- **Beamforming** (LCMV, DICS): spatial filtering approach, good for oscillatory sources.
- **Minimum-norm estimation (MNE)**: L2-norm solution, favors superficial sources.
- **dSPM**: noise-normalized MNE.

All require a **forward model** (BEM or sphere) and **source space** (cortical surface or volume grid).
