# -*- coding: utf-8 -*-
#
# Copyright 2016 Ramil Nugmanov <stsouko@live.ru>
# This file is part of PREDICTOR.
#
# PREDICTOR is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
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
import uuid
from os import path
from .config import UPLOAD_PATH, StructureStatus, TaskStatus, ModelType, TaskType
from .models import Tasks, Structures, Additives, Models, Additivesets, Destinations
from .redis import RedisCombiner
from flask import Blueprint, url_for, send_from_directory, request
from flask_login import current_user
from flask_restful import reqparse, Resource, fields, marshal, abort, Api
from functools import wraps
from pony.orm import db_session, select, left_join
from validators import url
from werkzeug import datastructures

api_bp = Blueprint('api', __name__)
api = Api(api_bp)

redis = RedisCombiner()


class ModelTypeField(fields.Raw):
    def format(self, value):
        return ModelType(value)


taskstructurefields = dict(structure=fields.Integer, data=fields.String, temperature=fields.Float(298),
                           pressure=fields.Float(1),
                           todelete=fields.Boolean(False),
                           additives=fields.List(fields.Nested(dict(additive=fields.Integer, amount=fields.Float))),
                           models=fields.List(fields.Integer))

modelfields = dict(example=fields.String, description=fields.String, type=ModelTypeField, name=fields.String,
                   destinations=fields.List(fields.Nested(dict(host=fields.String, port=fields.Integer(6379),
                                                               password=fields.String, name=fields.String))))


@api_bp.route('/task/batch_file/<string:file>', methods=['GET'])
def batch_file(file):
    return send_from_directory(directory=UPLOAD_PATH, filename=file)


def get_model(_type):
    with db_session:
        return next(dict(model=m.id, name=m.name, description=m.description, type=m.type,
                         destinations=[dict(host=x.host, port=x.port, password=x.password, name=x.name)
                                       for x in m.destinations])
                    for m in select(m for m in Models if m.model_type == _type.value))


def get_additives():
    with db_session:
        return {a.id: dict(additive=a.id, name=a.name, structure=a.structure, type=a.type)
                for a in select(a for a in Additives)}


def get_models_list(skip_prep=True):
    with db_session:
        return {m.id: dict(model=m.id, name=m.name, description=m.description, type=m.type, example=m.example,
                           destinations=[dict(host=x.host, port=x.port, password=x.password, name=x.name)
                                         for x in m.destinations])
                for m in (select(m for m in Models if m.model_type in (ModelType.MOLECULE_MODELING.value,
                                                                       ModelType.REACTION_MODELING.value))
                if skip_prep else select(m for m in Models))}


def fetchtask(task, status):
    job = redis.fetch_job(task)
    if job is None:
        abort(403, message=dict(task='invalid id'))

    if not job:
        abort(500, message=dict(server='error'))

    if not job['is_finished']:
        abort(202, message=dict(task='not ready'))

    if job['result']['status'] != status:
        abort(403, message=dict(task=dict(status='incorrect')))

    if job['result']['user'] != current_user.id:
        abort(403, message=dict(task='access denied'))

    return job['result'], job['ended_at']


def format_results(task, status):
    result, ended_at = fetchtask(task, status)
    result['task'] = task
    result['date'] = ended_at.strftime("%Y-%m-%d %H:%M:%S")
    result['status'] = result['status'].value
    result['type'] = result['type'].value
    result.pop('jobs')
    for s in result['structures']:
        s['status'] = s['status'].value
        s['type'] = s['type'].value
        for m in s['models']:
            m.pop('destinations', None)
            m['type'] = m['type'].value
            for r in m.get('results', []):
                r['type'] = r['type'].value
        for a in s['additives']:
            a['type'] = a['type'].value
    return result


def authenticate(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated:
            return func(*args, **kwargs)

        abort(401, message=dict(user='not authenticated'))

    return wrapper


class AuthResource(Resource):
    method_decorators = [authenticate]


class AdminResource(Resource):
    pass
    #method_decorators = [authenticate]


class AvailableModels(Resource):
    def get(self):
        out = []
        for x in get_models_list().values():
            x.pop('destinations')
            x['type'] = x['type'].value
            out.append(x)
        return out, 200


class AvailableAdditives(Resource):
    def get(self):
        out = []
        for x in get_additives().values():
            x['type'] = x['type'].value
            out.append(x)
        return out, 200


class RegisterModels(AdminResource):
    def post(self):
        data = marshal(request.get_json(force=True), modelfields)
        models = data if isinstance(data, list) else [data]
        available = {x['name']: [(d['host'], d['port'], d['name']) for d in x['destinations']]
                     for x in get_models_list(skip_prep=False).values()}
        report = []
        for m in models:
            if m['destinations']:
                if m['name'] not in available:
                    with db_session:
                        new_m = Models(type=m['type'], name=m['name'],
                                       **{x: m[x] for x in ('description', 'example') if m[x]})

                        for d in m['destinations']:
                            Destinations(model=new_m, **{x: y for x, y in d.items() if y})

                    report.append(dict(model=new_m.id, name=new_m.name, description=new_m.description,
                                       type=new_m.type.value,
                                       example=new_m.example,
                                       destinations=[dict(host=x.host, port=x.port, name=x.name)
                                                     for x in new_m.destinations]))
                else:
                    tmp = []
                    with db_session:
                        model = Models.get(name=m['name'])
                        for d in m['destinations']:
                            if (d['host'], d['port'], d['name']) not in available[m['name']]:
                                tmp.append(Destinations(model=model, **{x: y for x, y in d.items() if y}))

                    if tmp:
                        report.append(dict(model=model.id, name=model.name, description=model.description,
                                           type=model.type.value, example=model.example,
                                           destinations=[dict(host=x.host, port=x.port, name=x.name)
                                                         for x in tmp]))
        return report, 201


''' ===================================================
    collector of modeled tasks (individually). return json
    ===================================================
'''


class ResultsTask(AuthResource):
    def get(self, task):
        try:
            task = int(task)
        except ValueError:
            abort(403, message=dict(task='invalid id'))

        with db_session:
            result = Tasks.get(id=task)
            if not result:
                return dict(message=dict(task='invalid id')), 403
            if result.user.id != current_user.id:
                return dict(message=dict(task='access denied')), 403

            structures = select(s for s in Structures if s.task == result)
            resulsts = left_join((s.id, r.attrib, r.value, r.type, m.name)
                                 for s in Structures for r in s.results for m in r.model
                                 if s.task == result)
            additives = left_join((s.id, a.amount, p.id, p.name, p.type, p.structure)
                                  for s in Structures for a in s.additives for p in a.additive
                                  if s.task == result)

            tmp1, tmp2 = {}, {}

            # todo: result refactoring
            for s, ra, rv, rt, m in resulsts:
                tmp1.setdefault(s, {}).setdefault(m, []).append(dict(key=ra, value=rv, type=rt))

            for s, aa, aid, an, at, af in additives:
                if aid:
                    tmp2.setdefault(s, []).append(dict(additive=aid, name=an, structure=af, type=at, amount=aa))
                else:
                    tmp2[s] = []

            return dict(task=result.id, status=TaskStatus.DONE.value,
                        date=result.create_date.strftime("%Y-%m-%d %H:%M:%S"),
                        type=result.task_type, user=result.user.id if result.user else None,
                        structures=[dict(structure=s.id, data=s.structure, is_reaction=s.isreaction,
                                         temperature=s.temperature, pressure=s.pressure, status=s.status,
                                         models=[dict(model=m, results=r) for m, r in tmp1[s.id].items()],
                                         additives=tmp2[s.id]) for s in structures]), 200

    def post(self, task):
        result, ended_at = fetchtask(task, TaskStatus.DONE)

        with db_session:
            _task = Tasks(task_type=result['type'], date=ended_at)
            for s in result['structures']:
                _structure = Structures(structure=s['data'], isreaction=s['is_reaction'], temperature=s['temperature'],
                                        pressure=s['pressure'], status=s['status'])
                for a in s['additives']:
                    Additivesets(additive=Additives[a['additive']], structure=_structure, amount=a['amount'])

                    # todo: save results

        return dict(task=_task.id, status=TaskStatus.DONE.value, date=ended_at.strftime("%Y-%m-%d %H:%M:%S"),
                    type=_task.task_type, user=_task.user.id), 201


''' ===================================================
    api for task modeling.
    ===================================================
'''


class ModelTask(AuthResource):
    def get(self, task):
        return format_results(task, TaskStatus.DONE), 200

    def post(self, task):
        result = fetchtask(task, TaskStatus.PREPARED)[0]
        if result['type'] != TaskType.MODELING:  # for search tasks assign compatible models
            for s in result['structures']:
                s['models'] = [get_model(ModelType.select(s['type'], result['type']))]

        result['status'] = TaskStatus.MODELING

        newjob = redis.new_job(result)
        return dict(task=newjob['id'], status=result['status'].value, type=result['type'].value,
                    date=newjob['created_at'].strftime("%Y-%m-%d %H:%M:%S"), user=result['user']), 201


class PrepareTask(AuthResource):
    """ ===================================================
        api for task preparation.
        ===================================================
    """
    def get(self, task):
        return format_results(task, TaskStatus.PREPARED), 200

    def post(self, task):
        data = marshal(request.get_json(force=True), taskstructurefields)
        result = fetchtask(task, TaskStatus.PREPARED)[0]

        additives = get_additives()
        models = get_models_list()
        preparer = get_model(ModelType.PREPARER)

        prepared = {}
        for s in result['structures']:
            if s['status'] == StructureStatus.RAW:  # for raw structures restore preparer
                s['models'] = [preparer]
            prepared[s['structure']] = s

        structures = data if isinstance(data, list) else [data]
        tmp = {x['structure']: x for x in structures if x['structure'] in prepared}

        report = False
        for s, d in tmp.items():
            report = True
            if d['todelete']:
                prepared.pop(s)
            else:
                if d['additives'] is not None:
                    alist = []
                    for a in d['additives']:
                        if a['additive'] in additives and 0 < a['amount'] < 1:
                            a.update(additives[a['additive']])
                            alist.append(a)
                    prepared[s]['additives'] = alist

                if result['type'] == TaskType.MODELING and d['models'] is not None and \
                        not d['data'] and prepared[s]['status'] == StructureStatus.CLEAR:
                    prepared[s]['models'] = [models[m] for m in d['models']
                                             if m in models and
                                             models[m]['type'].compatible(prepared[s]['type'], TaskType.MODELING)]

                if d['data']:
                    prepared[s]['data'] = d['data']
                    prepared[s]['status'] = StructureStatus.RAW
                    prepared[s]['models'] = [preparer]

                if d['temperature']:
                    prepared[s]['temperature'] = d['temperature']

                if d['pressure']:
                    prepared[s]['pressure'] = d['pressure']

        if not report:
            abort(415, message=dict(structures='invalid data'))

        result['structures'] = list(prepared.values())
        result['status'] = TaskStatus.PREPARING
        new_job = redis.new_job(result)

        if new_job is None:
            abort(500, message=dict(server='error'))

        return dict(task=new_job['id'], status=result['status'].value, type=result['type'].value,
                    date=new_job['created_at'].strftime("%Y-%m-%d %H:%M:%S"), user=result['user']), 201


class CreateTask(AuthResource):
    """ ===================================================
        api for task creation.
        ===================================================
    """
    def post(self, _type):
        try:
            _type = TaskType(_type)
        except ValueError:
            abort(403, message=dict(task=dict(type='invalid id')))

        data = marshal(request.get_json(force=True), taskstructurefields)

        additives = get_additives()

        preparer = get_model(ModelType.PREPARER)
        structures = data if isinstance(data, list) else [data]

        data = []
        for s, d in enumerate(structures, start=1):
            if d['data']:
                alist = []
                for a in d['additives'] or []:
                    if a['additive'] in additives and 0 < a['amount'] < 1:
                        a.update(additives[a['additive']])
                        alist.append(a)

                data.append(dict(structure=s, data=d['data'], status=StructureStatus.RAW,
                                 pressure=d['pressure'], temperature=d['temperature'],
                                 additives=alist, models=[preparer]))

        if not data:
            return dict(message=dict(structures='invalid data')), 415

        new_job = redis.new_job(dict(status=TaskStatus.NEW, type=_type, user=current_user.id, structures=data))

        if new_job is None:
            abort(500, message=dict(server='error'))

        return dict(task=new_job['id'], status=TaskStatus.PREPARING.value, type=_type.value,
                    date=new_job['created_at'].strftime("%Y-%m-%d %H:%M:%S"), user=current_user.id), 201


uf_post = reqparse.RequestParser()
uf_post.add_argument('file.url', type=str)
uf_post.add_argument('file.path', type=str)
uf_post.add_argument('structures', type=datastructures.FileStorage, location='files')


class UploadTask(AuthResource):
    def post(self, _type):
        try:
            _type = TaskType(_type)
        except ValueError:
            abort(403, message=dict(task=dict(type='invalid id')))

        args = uf_post.parse_args()

        if args['file.url'] and url(args['file.url']):
            # smart frontend
            file_url = args['file.url']
        elif args['file.path'] and path.exists(path.join(UPLOAD_PATH, path.basename(args['file.path']))):
            # NGINX upload
            file_url = url_for('.batch_file', file=path.basename(args['file.path']))
        elif args['structures']:
            # flask
            file_name = str(uuid.uuid4())
            args['structures'].save(path.join(UPLOAD_PATH, file_name))
            file_url = url_for('.batch_file', file=file_name)
        else:
            return dict(message=dict(structures='invalid data')), 415

        new_job = redis.new_job(dict(status=TaskStatus.NEW, type=_type, user=current_user.id,
                                     structures=[dict(data=dict(url=file_url), status=StructureStatus.RAW,
                                                      models=[get_model(ModelType.PREPARER)])]))
        if new_job is None:
            abort(500, message=dict(server='error'))

        return dict(task=new_job['id'], status=TaskStatus.PREPARING.value, type=_type.value,
                    date=new_job['created_at'].strftime("%Y-%m-%d %H:%M:%S"), user=current_user.id), 201


api.add_resource(CreateTask, '/task/create/<int:_type>')
api.add_resource(UploadTask, '/task/upload/<int:_type>')
api.add_resource(PrepareTask, '/task/prepare/<string:task>')
api.add_resource(ModelTask, '/task/model/<string:task>')
# api.add_resource(ResultsTask, '/task/results/<string:task>')
api.add_resource(AvailableAdditives, '/resources/additives')
api.add_resource(AvailableModels, '/resources/models')
api.add_resource(RegisterModels, '/admin/models')
