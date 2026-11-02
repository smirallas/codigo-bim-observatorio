from archive import Archive
from collector import collect_one
import argparse, json, os
parser=argparse.ArgumentParser()
parser.add_argument('command',choices=['migrate','capture','snapshot'])
parser.add_argument('source',nargs='?',choices=['rail'],default='rail')

args=parser.parse_args()
archive=Archive(os.environ['DATABASE_URL'])
archive.migrate()
result={'status':'migrated'} if args.command=='migrate' else collect_one(archive,'rail') if args.command=='capture' else archive.latest('rail',None)
print(json.dumps(result,ensure_ascii=False,indent=2))
