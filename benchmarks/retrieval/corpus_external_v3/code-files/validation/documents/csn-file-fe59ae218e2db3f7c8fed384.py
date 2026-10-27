import json
import os
import sys
import time
import socket
import redis
from redis.sentinel import Sentinel
import logging
import signal
import tornado.ioloop
import tornado.process
import subprocess
from tornadis import PubSubClient
from tornado import gen


def noop(i):
    return i


def env(identifier, default, type=noop):
    return type(os.getenv('SINGLE_BEAT_%s' % identifier, default))


class Config(object):
    REDIS_SERVER = env('REDIS_SERVER', 'redis://localhost:6379')
    REDIS_SENTINEL = env('REDIS_SENTINEL', None)
    REDIS_SENTINEL_MASTER = env('REDIS_SENTINEL_MASTER', 'mymaster')
    REDIS_SENTINEL_DB = env('REDIS_SENTINEL_DB', 0)
    IDENTIFIER = env('IDENTIFIER', None)
    LOCK_TIME = env('LOCK_TIME', 5, int)
    INITIAL_LOCK_TIME = env('INITIAL_LOCK_TIME', LOCK_TIME * 2, int)
    HEARTBEAT_INTERVAL = env('HEARTBEAT_INTERVAL', 1, int)
    HOST_IDENTIFIER = env('HOST_IDENTIFIER', socket.gethostname())
    LOG_LEVEL = env('LOG_LEVEL', 'warn')
    # wait_mode can be, supervisored or heartbeat
    WAIT_MODE = env('WAIT_MODE', 'heartbeat')
    WAIT_BEFORE_DIE = env('WAIT_BEFORE_DIE', 60, int)
    _host_identifier = None

    def check(self, cond, message):
        if not cond:
            raise Exception(message)

    def checks(self):
        self.check(self.LOCK_TIME < self.INITIAL_LOCK_TIME, "inital lock time must be greater than lock time")
        self.check(self.HEARTBEAT_INTERVAL < (self.LOCK_TIME / 2.0), "SINGLE_BEAT_HEARTBEAT_INTERVAL must be smaller than SINGLE_BEAT_LOCK_TIME / 2")
        self.check(self.WAIT_MODE in ('supervised', 'heartbeat'), 'undefined wait mode')
        if self.REDIS_SENTINEL:
            master = self._sentinel.discover_master(self.REDIS_SENTINEL_MASTER)
        else:
            self._redis.ping()

    def get_redis(self):
        if self.REDIS_SENTINEL:
            return self._sentinel.master_for(self.REDIS_SENTINEL_MASTER,
                                       redis_class=redis.Redis)
        return self._redis

    def rewrite_redis_url(self):
        
        if self.REDIS_SERVER.startswith('unix://') or \
                self.REDIS_SERVER.startswith('redis://') or \
                self.REDIS_SERVER.startswith('rediss://'):
            return self.REDIS_SERVER
        return 'redis://{}/'.format(self.REDIS_SERVER)

    def __init__(self):
        if self.REDIS_SENTINEL:
            sentinels = [tuple(s.split(':')) for s in self.REDIS_SENTINEL.split(';')]
            self._sentinel = redis.sentinel.Sentinel(sentinels,
                                                     db=self.REDIS_SENTINEL_DB,
                                                     socket_timeout=0.1)
        else:
            self._redis = redis.Redis.from_url(self.rewrite_redis_url())

    def get_async_redis_client(self):
        conn = self.get_redis().connection_pool\
            .get_connection('ping')
        host, port, password = conn.host, conn.port, conn.password
        client = PubSubClient(host=host, port=port, password=password, autoconnect=True)
        return client

    def get_host_identifier(self):
        
        if self._host_identifier:
            return self._host_identifier
        local_ip_addr = self.get_redis().connection_pool\
            .get_connection('ping')._sock.getsockname()[0]
        self._host_identifier = '{}:{}'.format(local_ip_addr, os.getpid())
        return self._host_identifier


config = Config()
config.checks()

numeric_log_level = getattr(logging, config.LOG_LEVEL.upper(), None)
logging.basicConfig(level=numeric_log_level)
logger = logging.getLogger(__name__)


def get_process_identifier(args):
    
    return '_'.join(args)


class State(object):
    PAUSED = 'PAUSED'
    RUNNING = 'RUNNING'
    WAITING = 'WAITING'
    RESTARTING = 'RESTARTING'


def is_process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except:
        return False


class Process(object):
    def __init__(self, args):
        self.args = args
        self.state = None
        self.t1 = time.time()

        self.identifier = config.IDENTIFIER or get_process_identifier(self.args[1:])

        signal.signal(signal.SIGTERM, self.sigterm_handler)
        signal.signal(signal.SIGINT, self.sigterm_handler)

        self.async_redis = config.get_async_redis_client()
        self.fence_token = 0
        self.sprocess = None
        self.pc = None
        self.state = 'WAITING'
        self.ioloop = tornado.ioloop.IOLoop.instance()
        self.ioloop.spawn_callback(self.wait_for_commands)

    def proc_exit_cb(self, exit_status):
        
        sys.exit(exit_status)

    def proc_exit_cb_noop(self, exit_status):
        pass

    def proc_exit_cb_restart(self, exit_status):
        
        self.spawn_process()

    def proc_exit_cb_state_set(self, exit_status):
        if self.state == State.PAUSED:
            self.state = State.WAITING
            self.sprocess.set_exit_callback(self.proc_exit_cb)

    def stdout_read_cb(self, data):
        sys.stdout.write(data.decode())

    def stderr_read_cb(self, data):
        sys.stdout.write(data.decode())

    def timer_cb_paused(self):
        pass

    def timer_cb_waiting(self):
        if self.acquire_lock():
            logger.info("acquired lock, spawning child process")
            return self.spawn_process()
        # couldnt acquire lock
        if config.WAIT_MODE == 'supervised':
            logger.debug("already running, will exit after %s seconds"
                          % config.WAIT_BEFORE_DIE)
            time.sleep(config.WAIT_BEFORE_DIE)
            sys.exit()

    def process_pid(self):
        
        if self.sprocess:
            return self.sprocess.pid
        return -1

    def timer_cb_running(self):
        rds = config.get_redis()
        # read current fence token
        redis_fence_token = rds.get("SINGLE_BEAT_{identifier}".format(identifier=self.identifier))

        if redis_fence_token:
            redis_fence_token = int(redis_fence_token.split(b":")[0])
        else:
            logger.error("fence token could not be read from Redis - assuming lock expired, trying to reacquire lock")
            if self.acquire_lock():
                logger.info("reacquired lock")
                redis_fence_token = self.fence_token
            else:
                logger.error("unable to reacquire lock, terminating")
                os.kill(os.getpid(), signal.SIGTERM)

        logger.debug("expected fence token: {} fence token read from Redis: {}".format(self.fence_token, redis_fence_token))

        if self.fence_token == redis_fence_token:
            self.fence_token += 1
            rds.set("SINGLE_BEAT_{identifier}".format(identifier=self.identifier),
                    "{}:{}:{}".format(self.fence_token, config.HOST_IDENTIFIER, self.process_pid()),
                    ex=config.LOCK_TIME)
        else:
            logger.error("fence token did not match - lock is held by another process, terminating")
            # send sigterm to ourself and let the sigterm_handler do the rest
            os.kill(os.getpid(), signal.SIGTERM)

    def timer_cb_restarting(self):
        
        self.timer_cb_running()

    def timer_cb(self):
        logger.debug("timer called %s state=%s",
                     time.time() - self.t1, self.state)
        self.t1 = time.time()
        fn = getattr(self, 'timer_cb_{}'.format(self.state.lower()))
        fn()

    def acquire_lock(self):
        rds = config.get_redis()
        return rds.execute_command("SET", "SINGLE_BEAT_{}".format(self.identifier),
                                   "{}:{}:{}".format(self.fence_token, config.HOST_IDENTIFIER, 0),
                                   "NX", "EX", config.INITIAL_LOCK_TIME)

    def sigterm_handler(self, signum, frame):
        
        assert(self.state in ('WAITING', 'RUNNING', 'PAUSED'))
        logger.debug("our state %s", self.state)
        if self.state == 'WAITING':
            return self.ioloop.stop()

        if self.state == 'RUNNING':
            logger.debug('already running sending signal to child - %s',
                         self.sprocess.pid)
            os.kill(self.sprocess.pid, signum)
        self.ioloop.stop()

    def run(self):
        self.pc = tornado.ioloop.PeriodicCallback(self.timer_cb, config.HEARTBEAT_INTERVAL * 1000)
        self.pc.start()
        self.ioloop.start()

    def spawn_process(self):
        STREAM = tornado.process.Subprocess.STREAM
        cmd = sys.argv[1:]
        env = os.environ

        self.state = State.RUNNING
        try:
            self.sprocess = tornado.process.Subprocess(cmd,
                        env=env,
                        stdin=subprocess.PIPE,
                        stdout=STREAM,
                        stderr=STREAM
                       )
        except FileNotFoundError:
            """
            if the file that we need to run doesn't exists
            we immediately exit.
            """
            logger.exception("file not found")
            return self.proc_exit_cb(1)

        self.sprocess.set_exit_callback(self.proc_exit_cb)
        #
        self.sprocess.stdout.read_until_close(streaming_callback=self.stdout_read_cb)
        self.sprocess.stderr.read_until_close(streaming_callback=self.stderr_read_cb)

    def cli_command_info(self, msg):
        info = ''
        if self.sprocess:
            if is_process_alive(self.sprocess.pid):
                info = 'pid: {}'.format(self.sprocess.pid)
        return info

    def cli_command_quit(self, msg):
        
        if self.state == State.RUNNING and self.sprocess and self.sprocess.proc:
            self.sprocess.proc.kill()
        else:
            sys.exit(0)

    def cli_command_pause(self, msg):
        
        info = ''
        if self.state == State.RUNNING and self.sprocess and self.sprocess.proc:
            self.sprocess.set_exit_callback(self.proc_exit_cb_noop)
            self.sprocess.proc.kill()
            info = 'killed'
            # TODO: check if process is really dead etc.
        self.state = State.PAUSED
        return info

    def cli_command_resume(self, msg):
        
        if self.state == State.PAUSED:
            self.state = State.WAITING

    def cli_command_stop(self, msg):
        
        info = ''
        if self.state == State.RUNNING and self.sprocess and self.sprocess.proc:
            self.state = State.PAUSED
            self.sprocess.set_exit_callback(self.proc_exit_cb_state_set)
            self.sprocess.proc.kill()
            info = 'killed'
            # TODO: check if process is really dead etc.
        return info

    def cli_command_restart(self, msg):
        
        info = ''
        if self.state == State.RUNNING and self.sprocess and self.sprocess.proc:
            self.state = State.RESTARTING
            self.sprocess.set_exit_callback(self.proc_exit_cb_restart)
            self.sprocess.proc.kill()
            info = 'killed'
            # TODO: check if process is really dead etc.
        return info

    def pubsub_callback(self, msg):
        logger.info("got command - %s", msg)

        if msg[0] != b'message':
            return

        try:
            cmd = json.loads(msg[2])
        except:
            logger.exception("exception on parsing command %s", msg)
            return

        fn = getattr(self, 'cli_command_{}'.format(cmd['cmd']), None)
        if not fn:
            logger.info('cli_command_{} not found'.format(cmd['cmd']))
            return

        logger.info("got command - %s running %s", msg[2], fn)
        info = fn(cmd)
        rds = config.get_redis()
        logger.info("reply to %s", cmd['reply_channel'])
        rds.publish(cmd['reply_channel'], json.dumps({
            'identifier': config.get_host_identifier(),
            'state': self.state,
            'info': info or ''
        }))

    @gen.coroutine
    def wait_for_commands(self):
        logger.info('subscribed to %s', 'SB_{}'.format(self.identifier))
        yield self.async_redis.pubsub_subscribe('SB_{}'.format(self.identifier))
        logger.debug('subcribed to redis channel %s', 'SB_{}'.format(self.identifier))
        while True:
            msg = yield self.async_redis.pubsub_pop_message()
            self.pubsub_callback(msg)


def run_process():
    process = Process(sys.argv[1:])
    process.run()


if __name__ == "__main__":
    run_process()
