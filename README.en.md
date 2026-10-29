<p align="center">
  <img src="figures/xilin_poem_xingshu.svg" alt="Viewed from across, a ridge; from the side, a peak. Far, near, high, low — never the same. You cannot know the true face of Mount Lu, only because you are within the mountain. — Su Shi" width="820">
</p>

<p align="center"><sub>Viewed from across, a ridge; from the side, a peak — far, near, high, low, never the same.<br>You cannot know the true face of Mount Lu, only because you are within the mountain.<br>— Su Shi, <i>Written on the Wall of Xilin Temple</i></sub></p>

<p align="center"><a href="README.md">简体中文</a> · <b>English</b></p>

<h1 align="center">HACHIMI-II</h1>

<p align="center">
  From role-play to <b>learner behavior modeling</b>: a student-simulation method that uses third-person prediction to counter large-model <i>competence leakage</i>.
</p>

<p align="center">
  Paper: <i>HACHIMI-II: From Role-Play to Learner Behavior Modeling for Faithful Student Simulation</i>
  (<a href="https://arxiv.org/abs/2610.19654">arXiv</a> · <a href="paper/HACHIMI-II.pdf">PDF</a>)
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2610.19654"><img src="https://img.shields.io/badge/arXiv-2610.19654-b31b1b" alt="arXiv"></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/Python-3.13-blue" alt="Python"></a>
  <a href="#datasets-and-tasks"><img src="https://img.shields.io/badge/datasets-5-success" alt="datasets"></a>
  <a href="#what-the-method-deliberately-avoids"><img src="https://img.shields.io/badge/paradigm-third--person%20prediction-orange" alt="paradigm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="license"></a>
</p>

---

## What this is

When you simply ask a large model to "play a student" and answer items or hold a dialogue, the role prompt describes the student but does not model what this learner knows or will do next, so the model fills the gap with **its own** competence. Simulated students then perform at a level set by the model, differ little from one another, and seldom make the errors that real students make. We call this **competence leakage**.

HACHIMI-II **models the learner's behavior** and recasts student simulation as **third-person prediction** of the learner's next action:

> **First describe the learner and the learner's current state in the third person, then generate the current single step of learner behavior within the boundaries of that state.**

See the contour of "Mount Lu" from outside the mountain first, then step back in to place a single stroke — instead of being "within the mountain" from the start.

It is instantiated in two settings:

- **Item-response simulation**: given a student's history and one target item, predict the student's response on that item (mathematics and natural science);
- **Tutoring-dialogue simulation**: given a tutor-student dialogue so far, predict only the next student turn.

---

## Key results

On five datasets, HACHIMI-II counters competence leakage and reproduces the structure of real student errors.

**Item response**: the highest response agreement, the smallest distance between the real and simulated distributions of per-student accuracy (W₁), and the highest student-ranking correlation.

| Dataset | Agree ↑ | W₁ ↓ | Student ρ ↑ | Strongest baseline W₁ |
|---|---|---|---|---|
| XES3G5M | **0.752** | **0.039** | **0.691** | 0.327 |
| Eedi | **0.606** | **0.046** | **0.703** | 0.119 |
| ENEM | **0.630** | **0.169** | **0.668** | 0.409 |

> Baseline accuracy follows the model's own competence rather than the real students: on ENEM the real mean is about 0.39 while baselines simulate about 0.82; on XES3G5M the real mean is about 0.83 while baselines simulate about 0.50. HACHIMI-II tracks the real level (ENEM 0.384, XES3G5M 0.828).

**Tutoring dialogue**: HACHIMI-II reproduces real errors with the same knowledge type, error locus, and error mechanism 1.8× and 5.1× as often as the strongest baseline.

| Dataset | Rec_struct ↑ | Strongest baseline Rec_struct | F1_err ↑ | Strongest baseline F1_err |
|---|---|---|---|---|
| Eedi QATD2k | **0.315** | 0.172 | **0.561** | 0.248 |
| Khan/CoMTA | **0.565** | 0.110 | **0.464** | 0.183 |

> Functional agreement (κ_func / MCC_func), error-state metrics (BAcc_err / MCC_err), error structure (Prec_struct / F1_struct), and the three ablations (without the persona prior, the learner state, or the behavior harness) are reported in the paper and in [`results/`](results/).

---

## Datasets and tasks

| Setting | Directory | Dataset | Size | Task |
|---|---|---|---|---|
| Item response | `static/xes/` | XES3G5M | 60 students × 96 items | elementary math responses |
| Item response | `static/eedi-static/` | Eedi | 480 students × 107 items | diagnostic math items |
| Item response | `static/enem/` | ENEM 2024 | 7,200 students × 24 items | natural-science items |
| Tutoring dialogue | `dynamic/eedi/` | Eedi QATD2k | 17,256 turns | next student turn |
| Tutoring dialogue | `dynamic/khan/` | Khan/CoMTA | 917 turns | next student turn |

The datasets are obtained from their public sources; this repository does not redistribute them. Cite the original releases:

- **XES3G5M**: a large-scale knowledge-tracing benchmark of elementary math items and student response logs.
- **Eedi**: diagnostic multiple-choice math items from the NeurIPS Education Challenge; the dialogue split uses question-anchored tutoring dialogues.
- **ENEM 2024**: the Brazilian national exam; the natural-science (Ciências da Natureza) section is used here.
- **Khan/CoMTA**: Khan Academy tutoring-accuracy dialogues.

Place the raw data under the paths referenced by each setting's config, or point the scripts at your own copies via the corresponding arguments.

---

## Quick start

```bash
git clone https://github.com/YL1N/HACHIMI-II.git
cd HACHIMI-II
pip install -r requirements.txt
```

The core pipeline relies on the Python standard library and talks to an OpenAI-compatible endpoint over HTTP. A few evaluation components additionally require `numpy` and `rouge_score`.

All entry scripts drive an OpenAI-compatible chat-completions endpoint through three shared arguments:

```bash
--llm_base_url <https://your-endpoint/v1>
--llm_model    <model-name>
--llm_api_key  <api-key-or-dummy>
```

The results in the paper use a Qwen3.5-397B backbone for simulation and a GPT-5.4 judge for evaluation, but any OpenAI-compatible model can be substituted.

```bash
# Item response: XES3G5M
python static/xes/run_student_conditioned_benchmark.py --llm_base_url ... --llm_model ... --llm_api_key ...

# Item response: Eedi / ENEM
python static/eedi-static/run_eedi_static_benchmark.py --llm_base_url ... --llm_model ... --llm_api_key ...
python static/enem/run_enem_static_benchmark.py        --llm_base_url ... --llm_model ... --llm_api_key ...

# Tutoring dialogue: Eedi QATD2k (main pipeline)
python dynamic/eedi/run_eedi_experiments.py --llm_base_url ... --llm_model ... --llm_api_key ...

# Tutoring dialogue: Khan/CoMTA
python dynamic/khan/run_khan_experiments.py --llm_base_url ... --llm_model ... --llm_api_key ...
```

Baselines are launched from `static/baselines/run_static_baselines.py` and `dynamic/baselines/run_dynamic_baselines.py`. Every entry script accepts `--dry_run` (or `--prepare_only`) for a no-network smoke test.

---

## Repository layout

```text
static/            item-response simulation
  xes/             XES3G5M, incl. cohort preparation (item pool filter, Rasch fits)
  eedi-static/     Eedi diagnostic items
  enem/            ENEM 2024 natural-science items (text and text+image)
  baselines/       item-response baselines (Direct RP / Prompt-C / Profile-C)
dynamic/           tutoring-dialogue simulation
  eedi/            Eedi QATD2k (main pipeline)
  khan/            Khan/CoMTA
  baselines/       dialogue baselines (plus Agent-Mem)
  evaluation/      rescoring of dialogue metrics from the judge labels
results/           metric summaries matching the paper's tables
paper/             the paper PDF
figures/           README assets
```

Item-response and dialogue simulation are kept apart; each dataset keeps its own entry script, configs, and source; raw data, caches, and run outputs are not committed.

Baselines: in item-response simulation Direct Role-Play receives the item only, Prompt-Constrained also receives the history summary, and Profile-Conditioned also receives the history summary and the student profile text. In dialogue simulation every baseline receives the question and the dialogue before the target turn; Profile-Conditioned adds a coarse profile and Agent-Style Memory adds a coarse profile and a short memory, both computed from the earlier turns.

---

## The method

Both settings share the same four steps:

```
student model → learner state → behavior harness compilation → harnessed generation and checking
```

| Step | Meaning |
|---|---|
| Student model | Who the learner is: a profile summarized from the visible history, matched to a HACHIMI-1M student persona as a prior |
| Learner state | How this learner will handle the current item or tutor turn: reachable knowledge, active error pattern, confidence, and the local interaction move |
| Behavior harness | A fixed mapping from the state to limits on generation: accessible knowledge and reasoning depth, the error to preserve, uncertainty, response mode, and step budget |
| Harnessed generation | Write this step of learner behavior within the harness, and regenerate it when it violates a constraint |

When transferring to a new task, **don't start by writing a prompt**: first decide which information each step needs, then fill it with the educational theory of that task.

---

## Results files and metric definitions

| File | Contents |
|------|----------|
| `static_metrics.csv` | Item-response main and supplementary metrics (agreement, Wasserstein-1, per-student Spearman/Pearson, per-item correlations) for all methods. |
| `dynamic_metrics.csv` | Dialogue main and supplementary metrics (functional-label kappa/MCC, error-state balanced accuracy/MCC/F1/kappa, error recall and precision, error-structure recall/precision/F1) for all methods. |
| `ablation_static_metrics.csv` | Item-response ablations, with the real and simulated mean per-student accuracy and the standard deviation of simulated per-student accuracy. |
| `ablation_dynamic_metrics.csv` | Dialogue ablations, same metrics as `dynamic_metrics.csv`. |
| `dynamic_error_destination.csv` | Shares of real-error turns on which each simulator produces an error with matching structure, an error with different structure, or no error. |
| `dynamic_confusion_counts.csv` | Turn counts by real and simulated functional label, from which `kappa_func` and `MCC_func` are computed. |

Wasserstein-1 is the mean absolute difference between the sorted real and simulated per-student accuracies; Spearman/Pearson are the standard rank and linear correlations; the standard deviation of simulated per-student accuracy is the population standard deviation over the students.

Dialogue metrics are computed from the stored judge labels by `dynamic/evaluation/rescore_dialogue_metrics.py`. `kappa_func` and `MCC_func` are Cohen's kappa and the multiclass Matthews correlation over the three functional labels. `BAcc_err`, `MCC_err`, `F1_err`, and `kappa_err` are computed over the binary error indicator. A real error counts as reproduced only when the simulated turn also contains an error and the knowledge type, error locus, and error mechanism all match: `Rec_struct` is the share of real errors reproduced, `Prec_struct` is the share of simulated errors that reproduce a real error, and `F1_struct` is their harmonic mean.

---

## Documentation

| Document | Contents |
|---|---|
| [`STATIC_SIMULATION_GUIDE.md`](STATIC_SIMULATION_GUIDE.md) | Method chain, data boundaries, and per-dataset arguments for item-response simulation |
| [`DYNAMIC_SIMULATION_GUIDE.md`](DYNAMIC_SIMULATION_GUIDE.md) | Method chain, data boundaries, and per-dataset arguments for dialogue simulation |
| `README.md` in each subdirectory | How to run that dataset or baseline |
| [`paper/HACHIMI-II.pdf`](paper/HACHIMI-II.pdf) | The paper; its appendix gives the prompts of the dialogue pipeline |

XES3G5M is a Chinese-language dataset, so some subject, grade, module-name, and question-text string literals in `static/xes` are kept in Chinese to match the original data; comments, log messages, and descriptions are in English.

---

## What the method deliberately avoids

- Role-playing the student directly;
- Skipping the third-person learner state;
- Putting real labels, future turns, or official evaluation annotations into the generation chain;
- Special-casing by item ID or student ID;
- Post-hoc editing of answers;
- Piling up "sound more like a student" prompt patches.

---

## The parable of Mount Lu

> Viewed from across, a ridge; from the side, a peak —
> far, near, high, low, never the same.
> You cannot know the true face of Mount Lu,
> only because you are within the mountain.

This poem is the methodological metaphor of HACHIMI-II.

- **A ridge from across, a peak from the side; far, near, high, low, never the same.** The same student looks different from different viewpoints — item answering is one facet, tutoring dialogue is another; ability level, error structure, and knowledge mastery each form their own "peak." Any single view is only a fragment.
- **You cannot know the true face of Mount Lu, only because you are within the mountain.** Asking a model to role-play the student in the first person *is* being "within the mountain": the model is trapped in its own competence and viewpoint, generating its own shadow (competence leakage) and never seeing the student's true face.

HACHIMI-II's move is to step out of the mountain first: **model the student as a state in the third person**, sketching the boundary contour of "Mount Lu" from the outside — and only then step back in to generate this single step of behavior within that boundary. Know the true face first; then place each ridge and peak.

---

## Citation

If this repository helps your research, please cite it:

```bibtex
@article{jiang2026hachimiii,
  title   = {{HACHIMI-II}: From Role-Play to Learner Behavior Modeling for Faithful Student Simulation},
  author  = {Jiang, Yilin and Tan, Fei and Yin, Xuanyu and Leng, Jing and Zhou, Aimin},
  journal = {arXiv preprint arXiv:2610.19654},
  year    = {2026}
}
```

The student persona prior comes from HACHIMI-1M:

```bibtex
@inproceedings{jiang2026hachimi,
  title     = {{HACHIMI}: Scalable and Controllable Student Persona Generation via Orchestrated Agents},
  author    = {Jiang, Yilin and Tan, Fei and Yin, Xuanyu and Leng, Jing and Zhou, Aimin},
  booktitle = {Findings of the Association for Computational Linguistics: ACL 2026},
  year      = {2026}
}
```

## License

Released under the [MIT License](LICENSE).
