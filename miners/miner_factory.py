from miners.bosminer import BOSminer
from miners.bmminer import BMMiner
from miners.cgminer import CGMiner
from miners.unknown import UnknownMiner
from API import APIError
import asyncio
import ipaddress
import json


class MinerFactory:
    def __init__(self):
        self.miners = {}

    async def get_miner(self, ip: ipaddress.ip_address) -> BOSminer or CGMiner or BMMiner or UnknownMiner:
        if ip in self.miners:
            return self.miners[ip]
        version_data = await self._get_version_data(ip)
        version = None
        if version_data:
            version = list(version_data['VERSION'][0].keys())
        if version:
            if "BOSminer" in version or "BOSminer+" in version:
                miner = BOSminer(str(ip))
            elif "CGMiner" in version:
                miner = CGMiner(str(ip))
            elif "BMMiner" in version:
                miner = BMMiner(str(ip))
            else:
                miner = UnknownMiner(str(ip))
        else:
            miner = UnknownMiner(str(ip))
        self.miners[ip] = miner
        return miner

    def clear_cached_miners(self):
        self.miners = {}

    @staticmethod
    async def _get_version_data(ip: ipaddress.ip_address) -> dict or None:
        for i in range(3):
            try:
                # open a connection to the miner
                fut = asyncio.open_connection(str(ip), 4028)
                # get reader and writer streams
                try:
                    reader, writer = await asyncio.wait_for(fut, timeout=7)
                except asyncio.exceptions.TimeoutError:
                    return None

                # create the command
                cmd = {"command": "version"}

                # send the command
                writer.write(json.dumps(cmd).encode('utf-8'))
                await writer.drain()

                # instantiate data
                data = b""

                # loop to receive all the data
                while True:
                    d = await reader.read(4096)
                    if not d:
                        break
                    data += d

                if data.endswith(b"\x00"):
                    data = json.loads(data.decode('utf-8')[:-1])
                else:
                    # some stupid whatsminers need a different command
                    fut = asyncio.open_connection(str(ip), 4028)
                    # get reader and writer streams
                    try:
                        reader, writer = await asyncio.wait_for(fut, timeout=7)
                    except asyncio.exceptions.TimeoutError:
                        return None

                    # create the command
                    cmd = {"command": "get_version"}

                    # send the command
                    writer.write(json.dumps(cmd).encode('utf-8'))
                    await writer.drain()

                    # instantiate data
                    data = b""

                    # loop to receive all the data
                    while True:
                        d = await reader.read(4096)
                        if not d:
                            break
                        data += d

                    data = data.decode('utf-8').replace("\n", "")
                    data = json.loads(data)

                # close the connection
                writer.close()
                await writer.wait_closed()
                # check if the data returned is correct or an error
                # if status isn't a key, it is a multicommand
                if "STATUS" not in data.keys():
                    for key in data.keys():
                        # make sure not to try to turn id into a dict
                        if not key == "id":
                            # make sure they succeeded
                            if data[key][0]["STATUS"][0]["STATUS"] not in ["S", "I"]:
                                # this is an error
                                raise APIError(data["STATUS"][0]["Msg"])
                else:
                    # check for stupid whatsminer formatting
                    if not isinstance(data["STATUS"], list):
                        if data["STATUS"] not in ("S", "I"):
                            raise APIError(data["Msg"])
                        else:
                            if "whatsminer" in data["Description"]:
                                return {'STATUS': [{'STATUS': 'S', 'When': 1635435132, 'Code': 22, 'Msg': 'CGMiner versions', 'Description': 'cgminer 4.9.2'}], 'VERSION': [{'CGMiner': '4.9.2', 'API': '3.7'}], 'id': 1}
                    # make sure the command succeeded
                    elif data["STATUS"][0]["STATUS"] not in ("S", "I"):
                        # this is an error
                        raise APIError(data["STATUS"][0]["Msg"])
                # return the data
                return data
            except OSError as e:
                if e.winerror == 121:
                    return None
                else:
                    print(ip, e)
            # except json.decoder.JSONDecodeError:
                # print("Decode Error @ " + str(ip) + str(data))
            # except Exception as e:
                # print(ip, e)
        return None
