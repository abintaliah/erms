#!/usr/bin/env python3
"""Exercise the production Tika Pipes-fork path against the approved corpus."""

from __future__ import annotations

import csv
import ast
import json
import os
import re
import statistics
import time
from collections import Counter
from pathlib import Path

from backend.services.text_indexer.tika import extract, extract_image_ocr, extract_pdf, self_test

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
TIKA_HOME = Path(os.environ["TEXT_INDEXER_TIKA_HOME"]).resolve()
TOKEN = re.compile(r"[\w]+",re.UNICODE)
ARABIC = re.compile(r"[\u0600-\u06ff]")
LATIN = re.compile(r"[A-Za-z]")


def tokens(value: str, script: str) -> list[str]:
    found=[word.casefold() for word in TOKEN.findall(value)]
    expression=ARABIC if script=="arabic" else LATIN
    return [word for word in found if expression.search(word)]


def recall(expected: list[str], actual: list[str]) -> float:
    wanted,found=Counter(expected),Counter(actual)
    return sum(min(count,found[word]) for word,count in wanted.items())/max(1,sum(wanted.values()))


def main() -> None:
    source=(ROOT/"generate_corpus.py").read_text(encoding="utf-8")
    tree=ast.parse(source)
    keep={"ENGLISH_RARE","ARABIC_RARE","ENGLISH_SENTENCES","ARABIC_SENTENCES","words","make_body"}
    nodes=[]
    for node in tree.body:
        if isinstance(node,(ast.Assign,ast.AnnAssign)):
            target=node.targets[0] if isinstance(node,ast.Assign) else node.target
            if isinstance(target,ast.Name) and target.id in keep: nodes.append(node)
        elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in keep: nodes.append(node)
    namespace={"re":re}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(ROOT/"generate_corpus.py"),"exec"),namespace)
    make_body=namespace["make_body"]
    self_test(TIKA_HOME)
    rows=list(csv.DictReader((ROOT/"manifest.csv").open(encoding="utf-8")))
    selected=[]
    for mode in ("english","arabic","mixed"):
        for format_name in ("docx","pdf","html"):
            selected.append(next(row for row in rows if row["format"]==format_name and row["language_mode"]==mode))
        selected.extend([row for row in rows if row["format"] in {"png","jpeg"} and row["language_mode"]==mode][:2])
    cases=[]
    for row in selected:
        source=(ROOT/row["path"]).resolve(); expected,_,_=make_body(int(row["id"]),row["topic"],row["language_mode"])
        started=time.perf_counter()
        if row["format"] in {"png","jpeg"}: output=extract_image_ocr(source,120)
        elif row["format"]=="pdf": output,_=extract_pdf(TIKA_HOME,source,120,1000,1024*1024*1024)
        else: output=extract(TIKA_HOME,source,120)
        elapsed=time.perf_counter()-started
        cases.append({"path":row["path"],"mode":row["language_mode"],"seconds":round(elapsed,3),
                      "english_recall":round(recall(tokens(expected,"english"),tokens(output,"english")),4),
                      "arabic_recall":round(recall(tokens(expected,"arabic"),tokens(output,"arabic")),4),
                      "marker_found":row["unique_marker"].casefold() in output.casefold()})
    for name,index,mode in (("scanned-english.pdf",575,"english"),("scanned-arabic.pdf",573,"arabic"),("scanned-mixed.pdf",574,"mixed")):
        source=(ROOT/"phase0-scanned-pdf"/name).resolve(); expected,_,_=make_body(index,rows[index-1]["topic"],mode)
        started=time.perf_counter(); output,ocr_used=extract_pdf(TIKA_HOME,source,120,1000,1024*1024*1024); elapsed=time.perf_counter()-started
        cases.append({"path":f"phase0-scanned-pdf/{name}","mode":mode,"seconds":round(elapsed,3),
                      "english_recall":round(recall(tokens(expected,"english"),tokens(output,"english")),4),
                      "arabic_recall":round(recall(tokens(expected,"arabic"),tokens(output,"arabic")),4),
                      "marker_found":f"wathiqrare{index:04d}" in output.casefold(),"ocr_used":ocr_used})
    english=[case for case in cases if case["mode"]=="english"]
    arabic=[case for case in cases if case["mode"]=="arabic"]
    result={"distribution":{"version":"4.0.0","sha512":"59970cecd51dbd22f51eec1f14bfdefdf660dd9cd6f726dd7ec5dfafcd089d80927d6034c7514f8d87571a05715126e984e5e07dbf6d9033d54075a19884b92a","fork_parser":"tika-pipes-fork-parser-4.0.0.jar"},
            "limits":{"wall_seconds":120,"heap_mib":768,"embedded_depth":0,"pages":1000},"cases":cases,
            "summary":{"case_count":len(cases),"marker_recall":round(sum(c["marker_found"] for c in cases)/len(cases),4),
                       "english_recall":round(sum(c["english_recall"] for c in english)/len(english),4),
                       "arabic_recall":round(sum(c["arabic_recall"] for c in arabic)/len(arabic),4),
                       "median_seconds":round(statistics.median(c["seconds"] for c in cases),3),
                       "max_seconds":max(c["seconds"] for c in cases)}}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__": main()
