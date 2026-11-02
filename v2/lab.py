"""Operaciones locales del laboratorio; no se exponen como escrituras HTTP."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from archive import Archive
from collector import collect_one
from engine import evaluate
from scenarios import all_scenarios
from sources import ADAPTERS, CATALOG


def report(archive):
    cases=[]
    for case in all_scenarios():
        counts={key:0 for key in ('candidate','no_candidate','not_evaluable')}
        for at in case['times']:
            result=evaluate(case['events'],case['train_ids'],at)
            counts[result['status']]+=1
        cases.append({'scenario':case['id'],'kind':case['kind'],'steps':len(case['times']),'outcomes':counts})
    sources=[]
    for source in CATALOG:
        snapshot=archive.latest(source)
        if snapshot:
            features=snapshot.pop('features')
            snapshot['features']=len(features)
            snapshot['with_observed_at']=sum(bool(f['properties'].get('observed_at')) for f in features)
            snapshot['with_speed']=sum(f['properties'].get('speed_m_s') is not None for f in features)
            snapshot['with_track']=sum(bool(f['properties'].get('track_id')) for f in features)
        sources.append({'source':source,'snapshot':snapshot})
    return {'checked_at':datetime.now(timezone.utc).isoformat(),'version':'2.5.0','scenarios':cases,'sources':sources,
            'conclusion':'La simulación comprueba la regla bajo sus supuestos. Las capturas reales sin vía, velocidad u observación individual no permiten evaluar anticipación histórica.',
            'public_deployment':False,'external_alerts':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('migrate')
    capture=commands.add_parser('capture');capture.add_argument('source',choices=ADAPTERS)
    replay=commands.add_parser('snapshot');replay.add_argument('source',choices=ADAPTERS);replay.add_argument('--at')
    commands.add_parser('report')
    network=commands.add_parser('import-network');network.add_argument('kind',choices=('railway','highways'))
    network.add_argument('--bbox',required=True,help='oeste,sur,este,norte; usa --bbox=... para valores negativos')
    network.add_argument('--max-pages',type=int,default=5000)
    network.add_argument('--page-size',type=int,default=5000)
    network.add_argument('--resume',type=int)
    commands.add_parser('import-schedule')
    commands.add_parser('weather-maps')
    gpkg=commands.add_parser('import-roads-gpkg');gpkg.add_argument('file',type=Path);gpkg.add_argument('--original',type=Path,required=True)
    gpkg.add_argument('--kind',choices=('railway','highways'),default='highways')
    import_file=commands.add_parser('import');import_file.add_argument('source',choices=ADAPTERS);import_file.add_argument('file',type=Path)
    import_file.add_argument('--attribution',required=True)
    import_file.add_argument('--kind',required=True,choices=('observation','forecast','reference','synthetic'))
    args=parser.parse_args()
    archive=Archive(os.environ['DATABASE_URL']);archive.migrate()
    if args.command=='migrate':result={'status':'migrated'}
    elif args.command=='capture':result=collect_one(archive,args.source)
    elif args.command=='snapshot':result=archive.latest(args.source,args.at)
    elif args.command=='report':result=report(archive)
    elif args.command=='import-network':
        from networks import import_network
        result=import_network(archive,args.kind,[float(value) for value in args.bbox.split(',')],max_pages=args.max_pages,page_size=args.page_size,resume=args.resume)
    elif args.command=='import-schedule':
        from schedule import import_schedule
        result=import_schedule(archive)
    elif args.command=='weather-maps':result=collect_one(archive,'weather_maps')
    elif args.command=='import-roads-gpkg':
        from geopackage import import_roads
        result=import_roads(archive,args.file,args.original,args.kind)
    else:
        original=args.file.read_bytes()
        if len(original)>15_000_000:raise ValueError('Archivo demasiado grande')
        received=datetime.now(timezone.utc).isoformat()
        features,published=ADAPTERS[args.source](original,received)
        source='synthetic:'+args.source if args.kind=='synthetic' else args.source
        for feature in features:
            feature['properties']['kind']=args.kind
        result=archive.add(source,received,original,features,args.kind,published,
                           {'file':args.file.name,'attribution':args.attribution,'adapter_version':'2.0.0'})
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
