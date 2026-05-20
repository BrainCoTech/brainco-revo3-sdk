#include <stdio.h>
#include <math.h>
#include "quintic_trajectory.h"

int main() {
    QuinticTraj traj;
    float start = 0.0f;
    float target = 80.0f;
    float duration = 2.0f;
    
    quintic_init(&traj, start, target, duration);
    
    printf("Trajectory initialized:\n");
    printf("p0: %.2f, p1: %.2f, T: %.2f\n", traj.p0, traj.p1, traj.T);
    printf("a3: %.2f, a4: %.2f, a5: %.2f\n\n", traj.a3, traj.a4, traj.a5);
    
    printf("Time(s) | Pos(deg) | Vel(dps) | Vel(rpm)\n");
    printf("----------------------------------------\n");
    
    float dt = 0.2f;
    for (float t = 0.0f; t <= duration + dt/2; t += dt) {
        float pos, vel_dps;
        quintic_get(&traj, t, &pos, &vel_dps);
        float vel_rpm = vel_dps * DPS_TO_RPM;
        printf("%5.2f   | %8.2f | %8.2f | %8.2f\n", t, pos, vel_dps, vel_rpm);
    }
    
    return 0;
}
