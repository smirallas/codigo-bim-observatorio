from archive import Archive
from geopackage import import_roads
import argparse, json, os
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('gpkg',type=Path);p.add_argument('zip',type=Path)
p.add_argument('--kind',choices=['railway','highways'],default='railway')
a=p.parse_args();archive=Archive(os.environ['DATABASE_URL']);archive.migrate()
print(json.dumps(import_roads(archive,a.gpkg,a.zip,a.kind)))
