from archive import Archive
from schedule import import_schedule
import json,os
print(json.dumps(import_schedule(Archive(os.environ['DATABASE_URL']))))
