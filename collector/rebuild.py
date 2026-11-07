"""Rebuild a fixed, offline demonstration without modifying source data."""
import argparse
import csv
import hashlib
import html
import json
import shutil
from collections import Counter
from pathlib import Path

import pandas as pd

from collector.config import load_config
from collector.derive import add_features
from collector.insights import compute_insights, compute_comparison
from collector.main import RAW_COLUMNS
from collector.progress import write_progress_json
from collector.quality import annotate_quality, language_status

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comparison_svg(item, title):
    labels, a, b = item['labels'], item['flop'], item['viral']
    peak = max([1] + a + b)
    bars = []
    for i, label in enumerate(labels):
        x = 90 + i * 100
        for j, (value, color) in enumerate([(a[i], '#b91c1c'), (b[i], '#0f766e')]):
            height = value / peak * 190
            bars.append(f'<rect x="{x+j*32}" y="{260-height:.1f}" width="28" height="{height:.1f}" fill="{color}"/><text x="{x+j*32+14}" y="{250-height:.1f}" text-anchor="middle" font-size="11">{value}%</text>')
        bars.append(f'<text x="{x+30}" y="285" text-anchor="middle" font-size="12">{html.escape(label)}</text>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 780 330" role="img"><rect width="780" height="330" fill="white"/><g font-family="Arial,sans-serif" fill="#18354b"><text x="30" y="28" font-size="18">'+html.escape(title)+'</text><text x="30" y="51" font-size="12">Red: within flop group (%) | Teal: within viral group (%)</text>'+''.join(bars)+'<text x="30" y="320" font-size="11">Pooled descriptive distributions; not the probability of success and not causal evidence.</text></g></svg>'


def rebuild(source, out, as_of=None):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out == source or source.is_relative_to(out) or out.is_relative_to(source):
        raise ValueError('Output must be separate from the source data directory')
    cfg = load_config(str(ROOT / 'config.yaml'))
    source_files = [source / n for n in ['videos.csv','channels.csv','runs.csv','channel_status.csv']]
    hashes = {p.name:digest(p) for p in source_files}
    runs = pd.read_csv(source / 'runs.csv')
    if as_of is None:
        if runs.empty: raise ValueError('No recorded run; supply --as-of explicitly')
        as_of = runs.iloc[-1]['started_at']
    df = pd.read_csv(source / 'videos.csv')
    df = df[RAW_COLUMNS].drop_duplicates('video_id', keep='last').reset_index(drop=True)
    df['published_at'] = pd.to_datetime(df['published_at'], utc=True, errors='raise')
    featured = annotate_quality(add_features(df, cfg.window_days, cfg.min_prior), as_of)
    out.mkdir(parents=True, exist_ok=True)
    featured.to_csv(out/'videos.csv', index=False)
    featured[featured['analysis_eligible']].to_csv(out/'analysis_videos.csv', index=False)
    for name in ['channels.csv','runs.csv','channel_status.csv']:
        shutil.copyfile(source/name, out/name)
    insights = compute_insights(out/'videos.csv', out/'channels.csv', out/'insights.json')
    comparison = compute_comparison(out/'videos.csv', out/'channels.csv', out/'comparison.json')
    write_progress_json(out/'runs.csv',out/'channel_status.csv',out/'videos.csv',out/'progress.json')
    manifest = {
        'as_of':str(as_of), 'source_hashes':hashes,
        'source_rows':len(df), 'qualified_rows':int(featured['analysis_eligible'].sum()),
        'language_status':featured['language_status'].value_counts().to_dict(),
        'qualified_channels':comparison['sample_channels'],
        'qualified_flops':comparison['totals']['flops'], 'qualified_virals':comparison['totals']['virals'],
        'exclusion_reasons':featured['exclusion_reason'].value_counts().to_dict(),
        'policy':'English-tagged only for comparison; unknown language retained for review. Age >=90 days at fixed recorded run start. Positive baseline and finite score. No historical raw records automatically recovered.',
        'limitations':['English tags are not independent audio verification','Cumulative views have unequal exposure ages','No per-video collection timestamp; recorded run start is an approximation','Prior history truncated by collection limits','Pooled distributions are descriptive; channel and topic confounding remains','Short duration does not establish Shorts format','Original run history describes the original collection, not a new collection'],
    }
    audit=[]
    for _,ch in pd.read_csv(source/'channels.csv').iterrows():
        records=[]
        for path in sorted((source/'raw'/ch['channel_id']).glob('*.json')):
            records.append(json.loads(path.read_text(encoding='utf-8')))
        group=featured[featured['channel_id']==ch['channel_id']]
        audit.append({'channel_id':ch['channel_id'],'title':ch['title'],'raw_files':len(records),'stored_videos':len(group),'qualified_videos':int(group['analysis_eligible'].sum()),'raw_language_tags':json.dumps(dict(Counter(str(r.get('default_audio_language') or 'unknown') for r in records))), 'note':'Raw directory may contain multiple attempts; not automatically merged.'})
    pd.DataFrame(audit).to_csv(out/'channel_audit.csv',index=False)
    manifest['raw_files_reviewed']=sum(x['raw_files'] for x in audit)
    manifest['source_files_unchanged']=all(digest(source/name)==value for name,value in hashes.items())
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    for key,title in [('title_length_buckets','Title length distributions'),('duration_buckets','Duration distributions')]:
        (out/(key+'.svg')).write_text(comparison_svg(comparison[key],title),encoding='utf-8')
    (out/'examples.html').write_text('<!doctype html><meta charset="utf-8"><title>Flop Lab examples</title><style>body{max-width:1000px;margin:40px auto;font:17px/1.7 Arial;padding:20px}img{width:100%}</style><h1>Exploratory examples</h1><p>Fixed snapshot: '+html.escape(str(as_of))+f'. Qualified videos: {manifest["qualified_rows"]}; channels: {manifest["qualified_channels"]}; flops: {manifest["qualified_flops"]}; virals: {manifest["qualified_virals"]}.</p><p>Each colour sums to 100% within its own outcome group. This is NOT the chance of a video becoming viral. These pooled charts do not control channel, topic or video-age differences.</p><img alt="Title length by outcome group" src="title_length_buckets.svg"><img alt="Duration by outcome group" src="duration_buckets.svg"><p>Duration bins are descriptive, not confirmed Shorts/live categories. Unknown-language videos are excluded; full policy and limitations are recorded in manifest.json.</p>',encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'data')
    parser.add_argument('--out',type=Path,default=ROOT/'results'/'demo')
    parser.add_argument('--as-of',default=None)
    args=parser.parse_args()
    rebuild(args.source,args.out,args.as_of)


if __name__=='__main__': main()
