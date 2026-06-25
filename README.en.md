<p align="center">
  <img src="figures/xilin_poem_xingshu.svg" alt="Viewed from across, a ridge; from the side, a peak. Far, near, high, low — never the same. You cannot know the true face of Mount Lu, only because you are within the mountain. — Su Shi, Written on the Wall of Xilin Temple" width="720">
</p>

<p align="center"><sub>Viewed from across, a ridge; from the side, a peak — far, near, high, low, never the same.<br>You cannot know the true face of Mount Lu, only because you are within the mountain.<br>— Su Shi, <i>Written on the Wall of Xilin Temple</i></sub></p>

<p align="center"><a href="README.md">简体中文</a> · <b>English</b></p>

# HACHIMII

HACHIMII is not a collection of per-dataset scripts. It is a meta-method implementation repository for student simulation.

The core idea is:

> Model the learner state in the third person first, then generate the current single step of learner behavior within the boundaries of that state.

It applies to:

- **Static simulation**: single-item, single-step student answering;
- **Dynamic simulation**: multi-turn, step-by-step student interaction.

---

## 1. Where to start

If this is your first time in the repository, read in this order:

1. Meta-method overview: `META_METHOD_GUIDE.md`
2. Codex / agent porting playbook: `AGENT_META_METHOD_PLAYBOOK.md`
3. Overall method report: `reports/hachimii_meta_method_report_20260601.md`
4. Static method guide: `STATIC_SIMULATION_GUIDE.md`
5. Dynamic method guide: `DYNAMIC_SIMULATION_GUIDE.md`
6. Multi-dataset expansion plan: `DATASET_EXPANSION_PLAN.md`

---

## 2. Repository structure

```text
static/
  xes/           # XES static math item-response simulation
  eedi-static/   # EEDI static math diagnostic-item simulation
  enem/          # ENEM natural-science static cross-subject simulation

dynamic/
  eedi/          # EEDI / QATD2k dynamic tutoring-dialogue simulation
  khan/          # Khan / CoMTA dynamic tutoring-dialogue transfer experiment
```

Principles:

- `static/` and `dynamic/` are separated by simulation modality;
- each dataset keeps its own entry point, config, reports, and source;
- no top-level unifying wrapper;
- raw data, caches, and experiment outputs stay out of Git.

---

## 3. The shared meta-method interface

The common skeleton of HACHIMII is:

`Learner Context -> Task / Interaction Context -> Learner-Task Fit -> State Layer -> Harness / Constraint -> Surface Realization`

Meaning:

- `Learner Context`: who this learner is;
- `Task / Interaction Context`: what the current task or dialogue turn is;
- `Learner-Task Fit`: how this learner fares against this task;
- `State Layer`: the third-person state judgment made before generation;
- `Harness / Constraint`: translating the state into generation boundaries;
- `Surface Realization`: the current single step of learner behavior.

When porting to a new task, do not start by writing prompts. First fix what information each slot needs, then fill it with the educational theory specific to that task.

---

## 4. What the method deliberately avoids

Explicitly out of scope:

- no direct role-play of the student;
- no skipping the third-person state layer;
- no putting real labels, future replies, or official evaluation annotations into the generation chain;
- no special-casing by item id or student id;
- no post-hoc editing of answers;
- no piling on "make it more student-like" prompt patches to fake results.

---

## 5. In one sentence

What this repository records is:

> one student-simulation meta-method, instantiated across static item answering, dynamic tutoring dialogue, and both mathematics and natural-science tasks.

---

## The parable of Mount Lu

> Viewed from across, a ridge; from the side, a peak —
> far, near, high, low, never the same.
> You cannot know the true face of Mount Lu,
> only because you are within the mountain.

This poem is the methodological metaphor of HACHIMII.

- **A ridge from across, a peak from the side; far, near, high, low, never the same.** The same student looks different from different viewpoints — item answering is one facet, tutoring dialogue is another; ability level, error structure, and knowledge mastery each form their own "peak." Any single view is only a fragment.
- **You cannot know the true face of Mount Lu, only because you are within the mountain.** Asking a model to role-play the student in the first person *is* being "within the mountain": the model is trapped in its own competence and viewpoint, generating its own shadow (competence leakage) and never seeing the student's true face.

HACHIMII's move is to step out of the mountain first: **model the student as a state in the third person**, sketching the boundary contour of "Mount Lu" from the outside — and only then step back in to generate this single step of behavior within that boundary. Know the true face first; then place each ridge and peak.

---

> One student-simulation meta-method, instantiated across static answering, dynamic tutoring dialogue, mathematics, and natural science.
