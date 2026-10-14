# Computes the dialogue metrics reported in the paper from stored judge labels.
# Expected layout: <root>/<dataset>/<method>/eval_results.jsonl. No generation or judge call is made.
# Usage: python rescore_dialogue_metrics.py --root <results/dynamic> > dynamic_metrics.csv
import argparse, json, math, collections, csv, sys
_parser = argparse.ArgumentParser()
_parser.add_argument("--root", required=True, help="directory with <dataset>/<method>/eval_results.jsonl")
ROOT = _parser.parse_args().root.rstrip("/\\")
DS = {"eedi_qatd2k": "Eedi QATD2k", "khan_comta": "Khan/CoMTA"}
M = [("direct_roleplay","Direct RP"),("strong_prompting_ess","Prompt-C"),("profile_conditioned","Profile-C"),
     ("agent_style_memory","Agent-Mem"),("hachimi_ii","HACHIMI-II"),
     ("without_hachimi_prior","w/o Prior"),("without_task_local_state","w/o State"),("without_behavior_harness","w/o Harness")]
L = ["correct","incorrect","na"]

def norm_f(x):
    return x if x in ("correct","incorrect") else "na"

def parse(r):
    if "official_gt_correctness_label" in r:  # official format
        f, fh = norm_f(r["official_gt_correctness_label"]), norm_f(r["official_pred_correctness_label"])
        e, eh = bool(r.get("gold_has_codable_math_error")), bool(r.get("pred_has_codable_math_error"))
        g, p = r.get("gold_code") or {}, r.get("pred_code") or {}
        lab = [(g.get(k), p.get(k)) for k in ("knowledge_type","error_locus","error_mechanism")]
    else:
        f, fh = norm_f(r["real_function"]), norm_f(r["candidate_function"])
        e, eh = bool(r["real_has_codable_error"]), bool(r["candidate_has_codable_error"])
        lab = [(r["real_knowledge_type"], r["candidate_knowledge_type"]),
               (r["real_error_locus"], r["candidate_error_locus"]),
               (r["real_error_mechanism"], r["candidate_error_mechanism"])]
    return f, fh, e, eh, lab

def kappa_mcc(C):
    N = sum(map(sum, C)); t = [sum(r) for r in C]; p = [sum(C[i][j] for i in range(len(C))) for j in range(len(C))]
    po = sum(C[i][i] for i in range(len(C))) / N; pe = sum(t[k]*p[k] for k in range(len(C))) / N**2
    kap = (po-pe)/(1-pe) if pe < 1 else 0.0
    num = N*sum(C[k][k] for k in range(len(C))) - sum(t[k]*p[k] for k in range(len(C)))
    den = math.sqrt((N**2-sum(x*x for x in p))*(N**2-sum(x*x for x in t)))
    return kap, (num/den if den else 0.0)

out = []
for d, dn in DS.items():
    for m, mn in M:
        rows = [json.loads(l) for l in open(f"{ROOT}/{d}/{m}/eval_results.jsonl", encoding="utf-8")]
        C = [[0]*3 for _ in range(3)]; TP=FP=FN=TN=0; srec=[0,0,0]; joint=0; any1=0
        for r in rows:
            f, fh, e, eh, lab = parse(r)
            C[L.index(f)][L.index(fh)] += 1
            if e and eh:
                TP += 1
                ms = [a is not None and a == b for a, b in lab]
                for i in range(3): srec[i] += ms[i]
                joint += all(ms); any1 += any(ms)
            elif e: FN += 1
            elif eh: FP += 1
            else: TN += 1
        N = len(rows); E = TP+FN; Eh = TP+FP
        kf, mf = kappa_mcc(C); ke, me = kappa_mcc([[TP,FN],[FP,TN]])
        rec = TP/E; spec = TN/(TN+FP); prec = TP/Eh if Eh else 0
        jr = joint/E; jp = joint/Eh if Eh else 0
        out.append(dict(dataset=dn, method=mn, N=N, kappa_func=kf, MCC_func=mf, BAcc_err=(rec+spec)/2, MCC_err=me,
            kappa_err=ke, Calib=abs(Eh/N-E/N), SRec=sum(srec)/3/E, human_err_rate=E/N, sim_err_rate=Eh/N,
            error_recall=rec, error_precision=prec, F1_err=(2*prec*rec/(prec+rec) if prec+rec else 0),
            Rec_struct=jr, Prec_struct=jp, F1_struct=(2*jp*jr/(jp+jr) if jp+jr else 0), Struct_given_D=(joint/TP if TP else 0), SRec_type=srec[0]/E, SRec_locus=srec[1]/E, SRec_mech=srec[2]/E, dest_struct_match=jr, dest_struct_differs=rec-jr, dest_non_error=1-rec))
keys = list(out[0].keys())
w = csv.DictWriter(sys.stdout, keys); w.writeheader()
for o in out: w.writerow({k: (round(v,3) if isinstance(v,float) else v) for k,v in o.items()})
