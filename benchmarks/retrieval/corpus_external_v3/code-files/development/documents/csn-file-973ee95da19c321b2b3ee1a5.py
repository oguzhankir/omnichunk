

import asyncio
import logging
from functools import wraps

from qtm.packet import QRTPacketType, QRTPacket
from qtm.protocol import QTMProtocol, QRTCommandException

# pylint: disable=C0330

LOG = logging.getLogger("qtm")  # pylint: disable C0103


def validate_response(expected_responses):
    

    def internal_decorator(function):
        @wraps(function)
        async def wrapper(*args, **kwargs):

            response = await function(*args, **kwargs)

            for expected_response in expected_responses:
                if response.startswith(expected_response):
                    return response

            raise QRTCommandException(
                "Expected %s but got %s" % (expected_responses, response)
            )

        return wrapper

    return internal_decorator


class QRTConnection(object):
    

    def __init__(self, protocol: QTMProtocol, timeout):
        super(QRTConnection, self).__init__()
        self._protocol = protocol
        self._timeout = timeout

    def disconnect(self):
        
        self._protocol.transport.close()

    def has_transport(self):
        
        return self._protocol.transport is not None

    async def qtm_version(self):
        
        return await asyncio.wait_for(
            self._protocol.send_command("qtmversion"), timeout=self._timeout
        )

    async def byte_order(self):
        
        return await asyncio.wait_for(
            self._protocol.send_command("byteorder"), timeout=self._timeout
        )

    async def get_state(self):
        
        await self._protocol.send_command("getstate", callback=False)
        return await self._protocol.await_event()

    async def await_event(self, event=None, timeout=30):
        
        return await self._protocol.await_event(event, timeout=timeout)

    async def get_parameters(self, parameters=None):
        

        if parameters is None:
            parameters = ["all"]
        else:
            for parameter in parameters:
                if not parameter in [
                    "all",
                    "general",
                    "3d",
                    "6d",
                    "analog",
                    "force",
                    "gazevector",
                    "image",
                    "skeleton",
                    "skeleton:global",
                ]:
                    raise QRTCommandException("%s is not a valid parameter" % parameter)

        cmd = "getparameters %s" % " ".join(parameters)
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    async def get_current_frame(self, components=None) -> QRTPacket:
        

        if components is None:
            components = ["all"]
        else:
            _validate_components(components)

        cmd = "getcurrentframe %s" % " ".join(components)
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    async def stream_frames(self, frames="allframes", components=None, on_packet=None):
        

        if components is None:
            components = ["all"]
        else:
            _validate_components(components)

        self._protocol.set_on_packet(on_packet)

        cmd = "streamframes %s %s" % (frames, " ".join(components))
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    async def stream_frames_stop(self):
        

        self._protocol.set_on_packet(None)

        cmd = "streamframes stop"
        await self._protocol.send_command(cmd, callback=False)

    @validate_response([b"You are now master"])
    async def take_control(self, password):
        
        cmd = "takecontrol %s" % password
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    @validate_response([b"You are now a regular client"])
    async def release_control(self):
        

        cmd = "releasecontrol"
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    @validate_response([b"Creating new connection", b"Already connected"])
    async def new(self):
        
        cmd = "new"
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    @validate_response(
        [
            b"Closing connection",
            b"File closed",
            b"Closing file",
            b"No connection to close",
        ]
    )
    async def close(self):
        
        cmd = "close"
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    @validate_response([b"Starting measurement", b"Starting RT from file"])
    async def start(self, rtfromfile=False):
        
        cmd = "start" + (" rtfromfile" if rtfromfile else "")
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    @validate_response([b"Stopping measurement"])
    async def stop(self):
        
        cmd = "stop"
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    @validate_response([b"Measurement loaded"])
    async def load(self, filename):
        
        cmd = "load %s" % filename
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    @validate_response([b"Measurement saved"])
    async def save(self, filename, overwrite=False):
        
        cmd = "save %s%s" % (filename, " overwrite" if overwrite else "")
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    @validate_response([b"Project loaded"])
    async def load_project(self, project_path):
        
        cmd = "loadproject %s" % project_path
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    @validate_response([b"Trig ok"])
    async def trig(self):
        
        cmd = "trig"
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    @validate_response([b"Event set"])
    async def set_qtm_event(self, event=None):
        
        cmd = "event%s" % ("" if event is None else " " + event)
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )

    async def send_xml(self, xml):
        
        return await asyncio.wait_for(
            self._protocol.send_command(xml, command_type=QRTPacketType.PacketXML),
            timeout=self._timeout,
        )

        # TODO GetCaptureC3D
        # TODO GetCaptureQTM


async def connect(
    host,
    port=22223,
    version="1.19",
    on_event=None,
    on_disconnect=None,
    timeout=5,
    loop=None,
) -> QRTConnection:
    
    loop = loop or asyncio.get_event_loop()

    try:
        _, protocol = await loop.create_connection(
            lambda: QTMProtocol(
                loop=loop, on_event=on_event, on_disconnect=on_disconnect
            ),
            host,
            port,
        )
    except (ConnectionRefusedError, TimeoutError, OSError) as exception:
        LOG.error(exception)
        return None

    try:
        await protocol.set_version(version)
    except QRTCommandException as exception:
        LOG.error(Exception)
        return None
    except TypeError as exception:  # TODO: fix test requiring this (test_connect_set_version)
        LOG.error(exception)
        return None

    return QRTConnection(protocol, timeout=timeout)


def _validate_components(components):
    for component in components:
        if not component.lower() in [
            "all",
            "2d",
            "2dlin",
            "3d",
            "3dres",
            "3dnolabels",
            "3dnolabelsres",
            "force",
            "forcesingle",
            "6d",
            "6dres",
            "6deuler",
            "6deulerres",
            "gazevector",
            "image",
            "timecode",
            "skeleton",
            "skeleton:global",
        ]:
            raise QRTCommandException("%s is not a valid component" % component)

