
DBSession = None
Base = None

from .json import to_dict, from_dict

def config_sqlalchemy_rest(base, db_session):
    global Base
    Base = base
    base.to_dict = to_dict
    base.from_dict = from_dict
    global DBSession
    DBSession = db_session
