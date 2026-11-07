import hashlib
import json
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer

import pandas as pd
import pytest

from collector.derive import add_features, rolling_median_views
from collector.quality import language_status, annotate_quality
from collector.rebuild import rebuild
from collector.insights import compute_insights, compute_comparison


@pytest.mark.parametrize('value,expected',[('en','english'),('en-US','english'),('en-IN','english'),(' EN_gb ','english'),('es','other'),('english','other'),(None,'unknown'),(float('nan'),'unknown'),('','unknown')])
def test_language(value,expected):
    assert language_status(value)==expected


def test_strict_window_same_time_and_boundary():
    df=pd.DataFrame({'channel_id':['c']*4,'published_at':pd.to_datetime(['2025-01-01','2025-01-01','2025-04-01','2025-04-02']),'view_count':[100,300,500,600]})
    values=rolling_median_views(df,min_prior=1)
    assert pd.isna(values.iloc[0]) and pd.isna(values.iloc[1])
    assert values.iloc[2]==200  # exactly 90 days included
    assert values.iloc[3]==500  # day 91 excluded


def test_csv_tags_and_zero_baseline():
    df=pd.DataFrame({'channel_id':['c']*2,'published_at':pd.to_datetime(['2025-01-01','2025-01-02']),'view_count':[0,50],'title':['a','b'],'tags':["['a', 'b']",float('nan')]})
    result=add_features(df,min_prior=1)
    assert result['tag_count'].tolist()==[2,0]
    assert result['virality_score'].isna().all()


def test_offline_rebuild_reproducible_and_qualified(tmp_path):
    source=tmp_path/'source';source.mkdir()
    raw=pd.DataFrame({'video_id':[f'v{i}' for i in range(8)],'channel_id':['c']*8,'title':['Example 1?']*8,'published_at':pd.date_range('2025-01-01',periods=8,freq='D',tz='UTC'),'view_count':[100,100,100,100,100,10,500,200],'like_count':[1]*8,'comment_count':[1]*8,'duration_sec':[60]*8,'tags':["['a', 'b']"]*8,'category_id':['28']*8,'default_audio_language':['en-US']*7+[None],'channel_subs':[200000]*8})
    raw.to_csv(source/'videos.csv',index=False)
    pd.DataFrame([{'channel_id':'c','title':'Channel','niche':'tech','band':'(100000, 500000)','subscriber_count':200000}]).to_csv(source/'channels.csv',index=False)
    pd.DataFrame([{'run_id':'old','started_at':'2025-05-01T00:00:00Z','status':'success'}]).to_csv(source/'runs.csv',index=False)
    pd.DataFrame([{'channel_id':'c','title':'Channel','niche':'tech','status':'success'}]).to_csv(source/'channel_status.csv',index=False)
    original=(source/'videos.csv').read_bytes()
    out=tmp_path/'output';m=rebuild(source,out)
    assert m['qualified_rows']==2 and m['qualified_flops']==1 and m['qualified_virals']==1
    assert (source/'videos.csv').read_bytes()==original
    h=hashlib.sha256((out/'videos.csv').read_bytes()).hexdigest()
    rebuild(source,out)
    assert hashlib.sha256((out/'videos.csv').read_bytes()).hexdigest()==h
    insight=json.loads((out/'insights.json').read_text())
    assert insight['totals']['unknown']==5 and insight['totals']['neutral']==1
    with pytest.raises(ValueError):rebuild(source,source)


def test_demo_server_readonly_and_hides_credentials(tmp_path,monkeypatch):
    import serve
    (tmp_path/'manifest.json').write_text('{}')
    monkeypatch.setattr(serve,'DISPLAY_DATA',tmp_path)
    monkeypatch.setattr(serve,'DEMO_MODE',True)
    server=ThreadingHTTPServer(('127.0.0.1',0),serve.Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with urllib.request.urlopen(base+'/data/manifest.json') as r:assert r.status==200
        for path in ['/.env','/.git/config','/%2eenv']:
            with pytest.raises(urllib.error.HTTPError) as err:urllib.request.urlopen(base+path)
            assert err.value.code==404
        req=urllib.request.Request(base+'/api/run',data=b'{}',headers={'Content-Type':'application/json'})
        with pytest.raises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
        assert err.value.code==403
    finally:
        server.shutdown();server.server_close();thread.join()
