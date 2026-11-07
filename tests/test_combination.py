import json
from app.store import Store
from app.ingest import Upload
from app.worker import Worker


def test_persisted_map_observations_feed_final_candidate(tmp_path):
    store = Store(tmp_path/'db.sqlite3')
    up = Upload(store,'test.log')
    rows = [dict(client_ip='192.0.2.7',host='api',path='/login',username='user',auth_result='invalid_password') for i in range(5)]
    up.feed(('\n'.join(json.dumps(r) for r in rows)).encode())
    job = up.finish()
    call = store.new_call(job['id'],'map',{'tokens':[1],'fragments':[{'line':1,'offset':0,'text':json.dumps(rows[0])}]})
    store.finish_call(call,{'content':'{}','tokens_predicted':1},1,observations=[{'kind':'auth_failure','line':1}])
    candidates = Worker(store,None).combined_candidates(job['id'])
    assert candidates[0]['validated_map_signal_count']==1
    assert candidates[0]['model_observations']==[{'kind':'auth_failure','line':1}]
