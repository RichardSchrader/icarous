import sys
import os
import subprocess
import signal
import time
import datetime
import json
import yaml
import numpy as np
from pymavlink import mavutil, mavwp

sys.path.append("../Batch")
import BatchGSModule as GS

sim_home = os.getcwd()
icarous_home = os.path.abspath(os.path.join(sim_home, "../.."))
icarous_exe = os.path.join(icarous_home, "exe", "cpu1")


# Data structure to collect simulation data
def vehicle():
    return {"t": [], "position": [], "velocity": []}


def GetPolygons(origin, fenceList):
    """
    Constructs a list of Polygon (for use with PolyCARP) given a list of fences
    @param fenceList list of fence dictionaries
    @return list of polygons (a polygon here is a list of Vectors)
    """
    Polygons = []
    for fence in fenceList:
        vertices = fence["Vertices"]
        vertices_ned = [list(reversed(GS.LLA2NED(origin, position)))
                        for position in vertices]
        polygon = [(vertex[0], vertex[1]) for vertex in vertices_ned]
        Polygons.append(polygon)
    return Polygons


def GetWaypoints(wploader):
    '''extract waypoints'''
    WP = []
    for i in range(wploader.count()):
        if wploader.wp(i).command == 16:
            WP.append([wploader.wp(i).x, wploader.wp(i).y,
                       wploader.wp(i).z, wploader.wp(i).seq])
    return WP


def SetApps(sitl=False):
    '''set the apps that ICAROUS will run)'''
    if sitl:
        sim_app = "arducopter"
    else:
        sim_app = "rotorsim"

    app_list = ["Icarouslib","port_lib", "scheduler", sim_app, "gsInterface", "cognition",
                "guidance", "traffic", "trajectory", "geofence"]

    approot = os.path.join(icarous_home, "apps")
    outputloc = os.path.join(icarous_exe, "cf")

    subprocess.call(["python3", "../ConfigureApps.py",
                     approot, outputloc, *app_list])


def LaunchArducopter(scenario):
    wploader = mavwp.MAVWPLoader()
    wploader.load(os.path.join(icarous_home, scenario["waypoint_file"]))
    wp0 = wploader.wp(0)
    start_point = ','.join(str(x) for x in [wp0.x, wp0.y, wp0.z, 0])
    ap = subprocess.Popen(["sim_vehicle.py", "-v", "ArduCopter",
                           "-l", str(start_point)],
                          stdout=subprocess.DEVNULL)
    time.sleep(60)


def RunScenario(scenario, watch=False, save=False, verbose=True,
                out="14557", output_dir="", sitl=False):
    '''run an icarous simulation of the given scenario'''
    ownship = vehicle()
    traffic = {}
    name = scenario["name"].replace(' ', '-')

    # Clear message queue to avoid icarous problems
    messages = os.listdir("/dev/mqueue")
    for m in messages:
        os.remove(os.path.join("/dev/mqueue", m))

    # Set up mavlink connections
    gs_port = "14553"
    # Use mavproxy to forward mavlink stream (for visualization)
    if watch and not out:
        out = "14557"
    if out:
        gs_port = "14554"
        icarous_port = "14553"
        mav_forwarding = subprocess.Popen(["mavproxy.py",
                                           "--master=127.0.0.1:"+icarous_port,
                                           "--out=127.0.0.1:"+gs_port,
                                           "--out=127.0.0.1:"+out],
                                          stdout=subprocess.DEVNULL)
    # Optionally open up mavproxy with a map window to watch simulation
    if watch:
        logfile = os.path.join(output_dir, name+".tlog")
        mapwindow = subprocess.Popen(["mavproxy.py",
                                      "--master=127.0.0.1:"+out,
                                      "--target-component=5",
                                      "--load-module", "map,console",
                                      "--load-module", "traffic,geofence",
                                      "--logfile", logfile])
    # Open connection for virtual ground station
    try:
        master = mavutil.mavlink_connection("127.0.0.1:"+gs_port)
    except Exception as msg:
        print("Error opening mavlink connection")

    # Start the ICAROUS process
    os.chdir(icarous_exe)
    ic = subprocess.Popen(["./core-cpu1", "-I 0", "-C 1"],
                          stdout=subprocess.DEVNULL)

    # Pause for a couple of seconds here so that ICAROUS can boot up
    if verbose:
        print("Waiting for heartbeat...")
    master.wait_heartbeat()
    gs = GS.BatchGSModule(master, 1, 0)

    # Launch SITL simulator
    if sitl:
        LaunchArducopter(scenario)

    # Upload the flight plan
    gs.loadWaypoint(os.path.join(icarous_home, scenario["waypoint_file"]))
    # Read the flight plan
    WP = GetWaypoints(gs.wploader)
    origin = [WP[0][0], WP[0][1]]
    final = [WP[-1][0], WP[-1][1]]

    # Upload the geofence
    if scenario.get("geofence_file"):
        gs.loadGeofence(os.path.join(icarous_home, scenario["geofence_file"]))
    # Read the geofences
    GF = GetPolygons(origin, gs.fenceList)

    # Upload the icarous parameters
    if scenario.get("parameter_file"):
        gs.loadParams(os.path.join(icarous_home, scenario["parameter_file"]))
    if scenario.get("param_adjustments"):
        for param_id, param_value in scenario["param_adjustments"].items():
            gs.setParam(param_id, param_value)
    # Get the parameters
    params = gs.getParams()

    # Load traffic vehicles
    if scenario.get("traffic"):
        for traf in scenario["traffic"]:
            gs.load_traffic([0]+traf)

    # Wait for GPS fix before starting mission
    time.sleep(1)
    if verbose:
        print("Waiting for GPS fix...")
    master.recv_match(type="GLOBAL_POSITION_INT", blocking=True)

    if verbose:
        print("Starting mission")

    gs.StartMission()

    # Run simulation for specified duration
    simTimeLimit = scenario["time_limit"]
    startT = time.time()
    duration = 0
    alt = 0
    dist2final = 1000
    while duration < simTimeLimit:
        if verbose:
            print("Sim Duration: %.1fs\t Dist to Final: %.1fm\t Alt: %.1fm%s" %
                  (duration, dist2final, alt, " "*10), end="\r")
        time.sleep(0.01)
        currentT = time.time()
        duration = currentT - startT

        gs.Update_traffic()

        msg = master.recv_match(blocking=False, type=["GLOBAL_POSITION_INT"])

        if msg is None:
            continue

        # Store ownship position/velocity information
        ownship["t"].append(duration)
        ownship["position"].append([msg.lat/1E7, msg.lon/1E7,
                                    msg.relative_alt/1E3])
        ownship["velocity"].append([msg.vx/1E2, msg.vy/1E2,
                                    msg.vz/1E2])

        # Store traffic position/velocity information
        for i, traf in enumerate(gs.traffic_list):
            if i not in traffic.keys():
                traffic[i] = vehicle()
            traffic[i]["t"].append(duration)
            traffic[i]["position"].append([traf.lat, traf.lon, traf.alt])
            traffic[i]["velocity"].append([traf.vx0, traf.vy0, traf.vz0])

        # Check end conditions
        dist2final = GS.gps_distance(msg.lat/1E7, msg.lon/1E7,
                                     final[0], final[1])
        alt = ownship["position"][-1][2]
        if duration > 20 and dist2final < 5:
            if verbose:
                print("\nReached final waypoint")
            break

    # Once simulation is finished, kill the icarous process
    ic.kill()
    if out:
        subprocess.call(["kill", "-9", str(mav_forwarding.pid)])
    if watch:
        mapwindow.send_signal(signal.SIGINT)
        subprocess.call(["pkill", "-9", "mavproxy"])
    if sitl:
        subprocess.call(["pkill", "-9", "arducopter"])
        subprocess.call(["pkill", "-9", "xterm"])

    # Construct the sim data for verification
    simdata = {"geofences": GF,
               "waypoints": WP,
               "scenario": scenario,
               "params": params,
               "ownship": ownship,
               "traffic": traffic}

    # Save the sim data
    if save:
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)
        output_file = os.path.join(output_dir, "simoutput.json")
        f = open(output_file, 'w')
        json.dump(simdata, f)
        print("\nWrote sim data")
        f.close()

    return simdata


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Icarous test scenarios")
    parser.add_argument("scenario",
                        help="yaml file containing scenario(s) to run ")
    parser.add_argument("--test", action="store_true",
                        help="assert test conditions")
    parser.add_argument("--plot", action="store_true",
                        help="plot the simulation results")
    parser.add_argument("--save", action="store_true",
                        help="save the simulation results")
    parser.add_argument("--num", default="",
                        help="If multiple scenarios in file, just run this one")
    parser.add_argument("output_dir", nargs='?', default="simoutput",
                        help="directory to save output (default: 'simoutput')")
    parser.add_argument("--watch", action="store_true",
                        help="watch the simulation as it runs")
    parser.add_argument("--verbose", action="store_true",
                        help="print sim information")
    parser.add_argument("--out", nargs='?', default="",
                        help="localhost port to forward mavlink stream to (for visualization)")
    parser.add_argument("--validate", action="store_true",
                        help="check simulation results for test conditions")
    parser.add_argument("--sitl", action="store_true",
                        help="use arducopter SITL sim instead of rotorsim")
    parser.add_argument("--h_allow", type=float, default=0.85,
                        help="use h_allow*DTHR to check WC violation")
    parser.add_argument("--v_allow", type=float, default=0.85,
                        help="use v_allow*ZTHR to check WC violation")
    parser.add_argument("--wp_radius", type=float, default=5,
                        help="dist (m) to consider a waypoint reached")
    args = parser.parse_args()


    if args.watch:
        from matplotlib import pyplot as plt

    # Load scenarios
    if os.path.isfile(args.scenario):
        f = open(args.scenario, 'r')
        scenario_list = yaml.load(f, Loader=yaml.FullLoader)
        f.close()
    else:
        scenario_list = [json.loads(args.scenario)]

    if args.num:
        scenario_list = [scenario_list[int(args.num)]]
    if args.validate:
        import ValidateSim as VS

    # Set the apps that ICAROUS will run
    SetApps(sitl=args.sitl)

    results = []
    for i, scenario in enumerate(scenario_list):
        # Set up output directory
        name = scenario["name"].replace(' ', '-')
        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H_%M_%S")
        output_dir = os.path.join(sim_home, args.output_dir,
                                  timestamp+"_"+name)

        # Run the simulation
        print("\nRunning scenario: \"%s\"\t(%d/%d)\n" %
              (scenario["name"], i+1, len(scenario_list)))
        simdata = RunScenario(scenario, watch=args.watch,
                              save=args.save, verbose=args.verbose,
                              output_dir=output_dir, out=args.out,
                              sitl=args.sitl)

        # Verify the sim output
        if args.validate:
            validation_params = {"h_allow": args.h_allow,
                                 "v_allow": args.v_allow,
                                 "wp_radius": args.wp_radius}

            VF = VS.ValidateFlight(simdata, params=validation_params,
                                output_dir=output_dir)

            result = VF.validate_sim_data(test=args.test)
            results.append(result)

            if args.plot:
                VF.plot_scenario(save=args.save)


    # Print summary of results
    if args.validate:
        print("\nTest Scenario Results Summary:")
        print("------------------------------")
        for i in range(len(scenario_list)):
            VF.print_results(results[i], scenario_list[i]["name"])
