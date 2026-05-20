/**
 * @file quintic_trajectory.h
 * @brief Quintic polynomial trajectory interpolator for firmware-side debug.
 *
 * Boundary conditions: zero start/end velocity and acceleration.
 *
 * Polynomial:
 *   s(t) = a0 + a3*t^3 + a4*t^4 + a5*t^5
 *
 * Constraints:
 *   s(0) = start,  s(T) = target
 *   s'(0) = 0,     s'(T) = 0
 *   s''(0) = 0,    s''(T) = 0
 *
 * Solution:
 *   a0 = start
 *   a3 =  10 * h / T^3
 *   a4 = -15 * h / T^4
 *   a5 =   6 * h / T^5
 *   where h = target - start
 *
 * Usage in firmware:
 *   QuinticTraj traj;
 *   quintic_init(&traj, 0.0f, 80.0f, 2.0f);  // 0°→80° in 2s
 *
 *   // In 200Hz control loop:
 *   float pos_deg, vel_dps;
 *   quintic_get(&traj, t, &pos_deg, &vel_dps);
 *   float vel_rpm = vel_dps * DPS_TO_RPM;
 *   mit_control(joint_id, kp, kd, pos_deg, vel_rpm, 0.0f);
 *
 * Port of: python/revo3/mit_debug/trajectory.py (QuinticTrajectory)
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/* 1 rpm = 6 deg/s → 1 deg/s = 1/6 rpm */
#define DPS_TO_RPM  (1.0f / 6.0f)

typedef struct {
    float p0;       /* start position (deg) */
    float p1;       /* target position (deg) */
    float T;        /* duration (s) */
    float a3;       /* cubic coefficient */
    float a4;       /* quartic coefficient */
    float a5;       /* quintic coefficient */
} QuinticTraj;

/**
 * Initialize a quintic trajectory.
 * @param traj      Trajectory struct to fill.
 * @param start_pos Start position in degrees.
 * @param target_pos Target position in degrees.
 * @param duration  Trajectory duration in seconds (must be > 0).
 */
static inline void quintic_init(QuinticTraj *traj,
                                float start_pos,
                                float target_pos,
                                float duration)
{
    traj->p0 = start_pos;
    traj->p1 = target_pos;
    traj->T  = duration;

    float h  = target_pos - start_pos;
    float T2 = duration * duration;
    float T3 = T2 * duration;

    traj->a3 =  10.0f * h / T3;
    traj->a4 = -15.0f * h / (T3 * duration);
    traj->a5 =   6.0f * h / (T3 * T2);
}

/**
 * Evaluate trajectory at time t.
 * @param traj    Initialized trajectory.
 * @param t       Current time in seconds (from trajectory start).
 * @param pos_deg Output: position in degrees.
 * @param vel_dps Output: velocity in degrees-per-second.
 *
 * Values are clamped at boundaries when t < 0 or t > T.
 * To get velocity in RPM: vel_rpm = vel_dps * DPS_TO_RPM
 */
static inline void quintic_get(const QuinticTraj *traj,
                               float t,
                               float *pos_deg,
                               float *vel_dps)
{
    if (t <= 0.0f) {
        *pos_deg = traj->p0;
        *vel_dps = 0.0f;
        return;
    }
    if (t >= traj->T) {
        *pos_deg = traj->p1;
        *vel_dps = 0.0f;
        return;
    }

    float t2 = t * t;
    float t3 = t2 * t;
    float t4 = t3 * t;
    float t5 = t4 * t;

    *pos_deg = traj->p0 + traj->a3 * t3 + traj->a4 * t4 + traj->a5 * t5;
    *vel_dps = 3.0f * traj->a3 * t2 + 4.0f * traj->a4 * t3 + 5.0f * traj->a5 * t4;
}


/*==========================================================================
 * Pre-built joint parameters (matching tracking.py defaults)
 *==========================================================================*/

/* Per-joint safe close positions (degrees) */
static const float JOINT_CLOSE_POS[21] = {
    /* Pinky: Abd, MCP, PIP, DIP */
    12.0f, 80.0f, 80.0f, 80.0f,
    /* Ring:  Abd, MCP, PIP, DIP */
    12.0f, 80.0f, 80.0f, 80.0f,
    /* Mid:   Abd, MCP, PIP, DIP */
    12.0f, 80.0f, 80.0f, 80.0f,
    /* Index: Abd, MCP, PIP, DIP */
    12.0f, 80.0f, 80.0f, 80.0f,
    /* Thumb: Rot, MCP, IP */
    40.0f, 80.0f, 80.0f,
    /* Thumb: diff-1, diff-2 */
    90.0f, 100.0f,
};

/* Default MIT parameters */
#define DEFAULT_KP      5.0f
#define DEFAULT_KD      0.5f
#define DEFAULT_FREQ_HZ 200
#define DEFAULT_DT_MS   5       /* 1000 / 200 */
#define DEFAULT_DURATION 2.0f
#define DEFAULT_REPEAT   3

/*==========================================================================
 * Example firmware control loop (pseudo-code)
 *==========================================================================
 *
 * QuinticTraj traj;
 * int joint_id = 3;  // Pinky DIP
 * float open_pos = 0.0f;
 * float close_pos = JOINT_CLOSE_POS[joint_id];
 *
 * for (int rep = 0; rep < DEFAULT_REPEAT; rep++) {
 *     float p0 = (rep % 2 == 0) ? open_pos : close_pos;
 *     float p1 = (rep % 2 == 0) ? close_pos : open_pos;
 *     quintic_init(&traj, p0, p1, DEFAULT_DURATION);
 *
 *     for (int step = 0; step < (int)(DEFAULT_DURATION * DEFAULT_FREQ_HZ); step++) {
 *         float t = step * (1.0f / DEFAULT_FREQ_HZ);
 *         float pos, vel_dps;
 *         quintic_get(&traj, t, &pos, &vel_dps);
 *         float vel_rpm = vel_dps * DPS_TO_RPM;
 *
 *         // τ = Kp*(pos - act_pos) + Kd*(vel_rpm - act_vel) + 0
 *         mit_set(joint_id, DEFAULT_KP, DEFAULT_KD, pos, vel_rpm, 0.0f);
 *
 *         delay_ms(DEFAULT_DT_MS);
 *     }
 * }
 * // Release motor
 * mit_set(joint_id, 0, 0, 0, 0, 0);
 *
 *==========================================================================*/

#ifdef __cplusplus
}
#endif
