import re

import pylxd
from pylxd import exceptions

#TODO: improve exception handling based on how you plan to use this class
class LXDInstance:
    def __init__(self, instance_name):
        self.instance_name = instance_name
        self.client = pylxd.Client()

    def get_instance(self):
        instance_name = self.instance_name
        try:
            instance = self.client.instances.get(instance_name)
            return instance
        except exceptions.LXDAPIException as e:
            raise e

    def is_running(self):
        try:
            instance = self.get_instance()

            status = instance.status
            if status == "Running":
                return True

            return False
        except exceptions.LXDAPIException as e:
            raise e

    def list_gpu_profiles(self):
        try:
            instance = self.get_instance()

            gpu_profiles = [elem for elem in instance.profiles
                                    if re.match(r'^gpu\-[0-9]+\-[0-9a-zA-Z]+$',
                                                elem)]
            return gpu_profiles
        except exceptions.LXDAPIException as e:
            raise e

    def detach_gpu_profiles(self, force=False):
        try:
            instance = self.get_instance()

            is_running = self.is_running()
            if is_running:
                if not force:
                    raise Exception(f"Cannot detach profiles from {self.instance_name} when running")

                # stop the instance manually and wait until is stopped
                instance.stop(wait=True)

            gpu_profiles = self.list_gpu_profiles()
            for gprof in gpu_profiles:
                profile = self.client.profiles.get(gprof)
                instance.profiles.remove(gprof)

            # persist changes to instance
            instance.save()
        except exceptions.LXDAPIException as e:
            raise e

# simple test
if __name__ == "__main__":
    instance_name = "trusting-tahr"
    instance = LXDInstance(instance_name)

    print(instance.list_gpu_profiles())
    print(instance.is_running())

    instance.detach_gpu_profiles(True)
