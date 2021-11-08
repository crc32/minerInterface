import asyncio
import json
import ipaddress


class APIError(Exception):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return f"{self.message}"
        else:
            return "Incorrect API parameters."


class BaseMinerAPI:
    def __init__(self, ip: str, port: int = 4028) -> None:
        # api port, should be 4028
        self.port = port
        # ip address of the miner
        self.ip = ipaddress.ip_address(ip)

    def get_commands(self) -> list:
        """Get a list of command accessible to a specific type of API on the miner."""
        return [func for func in
                # each function in self
                dir(self) if callable(getattr(self, func)) and
                # no __ methods
                not func.startswith("__") and
                # remove all functions that are in this base class
                func not in
                [func for func in
                 dir(BaseMinerAPI) if callable(getattr(BaseMinerAPI, func))
                 ]
                ]

    async def multicommand(self, *commands: str) -> dict:
        """Creates and sends multiple commands as one command to the miner."""
        # split the commands into a proper list
        commands = [*commands]

        for item in commands:
            # make sure we can actually run the command, otherwise it will fail
            if item not in self.get_commands():
                # if the command isnt allowed, remove it
                print(f"Removing incorrect command: {item}")
                commands.remove(item)

        # standard multicommand format is "command1+command2"
        # doesnt work for S19 which is dealt with in the send command function
        command = "+".join(commands)
        return await self.send_command(command)

    async def send_command(self, command: str, parameters: str or int or bool = None) -> dict:
        """Send an API command to the miner and return the result."""
        try:
            # get reader and writer streams
            reader, writer = await asyncio.open_connection(str(self.ip), self.port)
        # handle OSError 121
        except OSError as e:
            if e.winerror == "121":
                print("Semaphore Timeout has Expired.")
            return {}

        # create the command
        cmd = {"command": command}
        if parameters is not None:
            cmd["parameter"] = parameters

        # send the command
        writer.write(json.dumps(cmd).encode('utf-8'))
        await writer.drain()

        # instantiate data
        data = b""

        # loop to receive all the data
        try:
            while True:
                d = await reader.read(4096)
                if not d:
                    break
                data += d
        except Exception as e:
            print(e)

        data = self.load_api_data(data)

        # close the connection
        writer.close()
        await writer.wait_closed()

        # validate the command suceeded
        # also handle for S19 not liking "command1+command2" format
        if not self.validate_command_output(data):
            try:
                data = {}
                # S19 handler, try again
                for cmd in command.split("+"):
                    data[cmd] = []
                    data[cmd].append(await self.send_command(cmd))
            except Exception as e:
                print(e)

        # check again after second try
        if not self.validate_command_output(data):
            raise APIError(data["STATUS"][0]["Msg"])

        return data

    @staticmethod
    def validate_command_output(data: dict) -> bool:
        """Check if the returned command output is correctly formatted."""
        # check if the data returned is correct or an error
        # if status isn't a key, it is a multicommand
        if "STATUS" not in data.keys():
            for key in data.keys():
                # make sure not to try to turn id into a dict
                if not key == "id":
                    # make sure they succeeded
                    if "STATUS" in data.keys():
                        if data[key][0]["STATUS"][0]["STATUS"] not in ["S", "I"]:
                            # this is an error
                            return False
        else:
            # make sure the command succeeded
            if data["STATUS"][0]["STATUS"] not in ("S", "I"):
                # this is an error
                if data["STATUS"][0]["STATUS"] not in ("S", "I"):
                    return False
        return True

    @staticmethod
    def load_api_data(data: bytes) -> dict:
        """Convert API data from JSON to dict"""
        try:
            # some json from the API returns with a null byte (\x00) on the end
            if data.endswith(b"\x00"):
                # handle the null byte
                data = json.loads(data.decode('utf-8')[:-1])
            else:
                # no null byte
                data = json.loads(data.decode('utf-8'))
        # handle bad json
        except json.decoder.JSONDecodeError:
            raise APIError(f"Decode Error: {data}")
        return data
