import datetime
import os

from flask import Flask
from flask_restful import Resource, Api, reqparse
from flask_cors import CORS
from flask_app.auth import requires_auth

from worker.tasks import process_vote
from common.utils import get_tasks_in_queue, db_cursor

vote_parser = reqparse.RequestParser()
vote_parser.add_argument('user_id', required=True, location="json")
vote_parser.add_argument('vote', required=True, location="json")


class Vote(Resource):
    def patch(self):
        """Use send a vote"""
        args = vote_parser.parse_args()
        process_vote.delay(
            user_id=args['user_id'],
            vote=args['vote'],
            update_dt=datetime.datetime.utcnow()
        )


class Stats(Resource):
    decorators = [requires_auth]

    def get(self):
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT
              coalesce(SUM(CAST(vote=1 as integer)), 0) as landscape,
              coalesce(SUM(CAST(vote=-1 as integer)), 0) as portrait
            FROM
              votes
            WHERE
              last_update >= NOW() - INTERVAL '15 minutes'
              """)
            landscape, portrait = cursor.fetchone()
            cursor.execute("""SELECT coalesce(SUM(count), 0) FROM votes""")
            count, = cursor.fetchone()

        status = dict(
            landscape=landscape,
            portrait=portrait,
            votes_processed=count
        )
        return status

class QueueDepth(Resource):
    decorators = [requires_auth]

    def get(self):
        url = os.environ['AMQP_URL']
        status = dict(
            queue_depth=get_tasks_in_queue(url)
        )
        return status


app = Flask(__name__)
api = Api(app)

api.add_resource(Vote, '/vote')
api.add_resource(Stats, '/stats')
api.add_resource(QueueDepth, '/queue-depth')


CORS(app,
     resources={r"/*": {"origins": "*"}},
     supports_credentials=True)  # http://stackoverflow.com/questions/3342140/cross-domain-cookies

if __name__ == '__main__':
    app.run(debug=True)

