# -*- coding: utf-8 -*-
#
# Copyright 2015 Ramil Nugmanov <stsouko@live.ru>
# Copyright 2015 Oleg Varlamov <ovarlamo@gmail.com>
# This file is part of PREDICTOR.
#
# PREDICTOR is free software; you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
from enum import Enum
from os import path


UPLOAD_PATH = 'upload'
PORTAL_BASE = ''
SECRET_KEY = 'development key'
DEBUG = False
HOST = '0.0.0.0'
PORT = 5000

LAB_NAME = 'Kazan Chemoinformatics and Molecular Modeling Laboratory'
LAB_SHORT = 'CIMM'
BLOG_POSTS = 10

DB_USER = None
DB_PASS = None
DB_HOST = None
DB_NAME = None

REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_PASSWORD = None
REDIS_TTL = 86400
REDIS_JOB_TIMEOUT = 3600


class StructureStatus(Enum):
    RAW = 0
    HAS_ERROR = 1
    CLEAR = 2


class StructureType(Enum):
    MOLECULE = 0
    REACTION = 1


class TaskStatus(Enum):
    NEW = 0
    PREPARING = 1
    PREPARED = 2
    MODELING = 3
    DONE = 4


class ModelType(Enum):
    PREPARER = 0
    MOLECULE_MODELING = 1
    REACTION_MODELING = 2
    MOLECULE_SIMILARITY = 3
    REACTION_SIMILARITY = 4
    MOLECULE_SUBSTRUCTURE = 5
    REACTION_SUBSTRUCTURE = 6

    @staticmethod
    def select(structure_type, task_type):
        return ModelType['%s_%s' % (structure_type.name, task_type.name)]

    def compatible(self, structure_type, task_type):
        return self.name == '%s_%s' % (structure_type.name, task_type.name)


class TaskType(Enum):
    MODELING = 0
    SIMILARITY = 1
    SUBSTRUCTURE = 2


class AdditiveType(Enum):
    SOLVENT = 0
    CATALYST = 1


class ResultType(Enum):
    TEXT = 0
    STRUCTURE = 1
    TABLE = 2
    IMAGE = 3
    GRAPH = 4
    GTM = 5


class UserRole(Enum):
    COMMON = 1
    ADMIN = 2


class BlogPost(Enum):
    COMMON = 1
    CAROUSEL = 2
    IMPORTANT = 3
    PROJECTS = 4
    TEAM = 5
    CHIEF = 6
    STUDENT = 7
    MEETING = 8


class Glyph(Enum):
    COMMON = 'file'
    CAROUSEL = 'camera'
    IMPORTANT = 'bullhorn'
    PROJECTS = 'hdd'
    TEAM = 'queen'
    CHIEF = 'king'
    STUDENT = 'pawn'
    MEETING = 'resize-small'


if not path.exists(path.join(path.dirname(__file__), "config.ini")):
    with open(path.join(path.dirname(__file__), "config.ini"), 'w') as f:
        f.write('\n'.join('%s = %s' % (x, y) for x, y in globals().items() if x in
                          ('UPLOAD_PATH', 'PORTAL_BASE', 'SECRET_KEY', 'HOST', 'PORT',
                           'DB_USER', 'DB_PASS', 'DB_HOST', 'DB_NAME',
                           'REDIS_HOST', 'REDIS_PORT', 'REDIS_PASSWORD', 'REDIS_TTL', 'REDIS_JOB_TIMEOUT',
                           'LAB_NAME', 'LAB_SHORT', 'BLOG_POSTS')))

with open(path.join(path.dirname(__file__), "config.ini")) as f:
    for line in f:
        try:
            k, v = line.split('=')
            k = k.strip()
            v = v.strip()
            if k in ('UPLOAD_PATH', 'PORTAL_BASE', 'SECRET_KEY', 'HOST', 'PORT', 'DEBUG',
                     'DB_USER', 'DB_PASS', 'DB_HOST', 'DB_NAME',
                     'REDIS_HOST', 'REDIS_PORT', 'REDIS_PASSWORD', 'REDIS_TTL', 'REDIS_JOB_TIMEOUT',
                     'LAB_NAME', 'LAB_SHORT', 'BLOG_POSTS'):
                globals()[k] = int(v) if v.isdigit() else v
        except:
            pass
