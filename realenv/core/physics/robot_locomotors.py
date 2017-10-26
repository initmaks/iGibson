from realenv.core.physics.robot_bases import MJCFBasedRobot
import numpy as np
import pybullet as p
import os
from transforms3d.euler import euler2quat
from realenv.data.datasets import get_model_initial_pose


def quatWXYZ2quatXYZW(wxyz):
	return np.concatenate((wxyz[1:], wxyz[:1]))

class WalkerBase(MJCFBasedRobot):
	def __init__(self, fn, robot_name, action_dim, obs_dim, power):
		MJCFBasedRobot.__init__(self, fn, robot_name, action_dim, obs_dim)
		self.power = power
		self.camera_x = 0
		self.walk_target_x = 1e3  # kilometer away
		self.walk_target_y = 0
		self.body_xyz=[0,0,0]


	def robot_specific_reset(self):
		for j in self.ordered_joints:
			j.reset_current_position(self.np_random.uniform(low=-0.1, high=0.1), 0)

		self.feet = [self.parts[f] for f in self.foot_list]
		self.feet_contact = np.array([0.0 for f in self.foot_list], dtype=np.float32)

		self.scene.actor_introduce(self)
		self.initial_z = None

	def apply_action(self, a):
		assert (np.isfinite(a).all())
		print("ordered joints", len(self.ordered_joints))
		for n, j in enumerate(self.ordered_joints):
			print(n, a[n])
			j.set_motor_torque(self.power * j.power_coef * float(np.clip(a[n], -1, +1)))

	def calc_state(self):
		j = np.array([j.current_relative_position() for j in self.ordered_joints], dtype=np.float32).flatten()
		# even elements [0::2] position, scaled to -1..+1 between limits
		# odd elements  [1::2] angular speed, scaled to show -1..+1
		self.joint_speeds = j[1::2]
		self.joints_at_limit = np.count_nonzero(np.abs(j[0::2]) > 0.99)

		body_pose = self.robot_body.pose()
		parts_xyz = np.array([p.pose().xyz() for p in self.parts.values()]).flatten()
		self.body_xyz = (
		parts_xyz[0::3].mean(), parts_xyz[1::3].mean(), body_pose.xyz()[2])  # torso z is more informative than mean z
		self.body_rpy = body_pose.rpy()
		z = self.body_xyz[2]
		if self.initial_z == None:
			self.initial_z = z
		r, p, yaw = self.body_rpy
		self.walk_target_theta = np.arctan2(self.walk_target_y - self.body_xyz[1],
											self.walk_target_x - self.body_xyz[0])
		self.walk_target_dist = np.linalg.norm(
			[self.walk_target_y - self.body_xyz[1], self.walk_target_x - self.body_xyz[0]])
		angle_to_target = self.walk_target_theta - yaw

		rot_speed = np.array(
			[[np.cos(-yaw), -np.sin(-yaw), 0],
			 [np.sin(-yaw), np.cos(-yaw), 0],
			 [		0,			 0, 1]]
		)
		vx, vy, vz = np.dot(rot_speed, self.robot_body.speed())  # rotate speed back to body point of view

		more = np.array([ z-self.initial_z,
			np.sin(angle_to_target), np.cos(angle_to_target),
			0.3* vx , 0.3* vy , 0.3* vz ,  # 0.3 is just scaling typical speed into -1..+1, no physical sense here
			r, p], dtype=np.float32)
		return np.clip( np.concatenate([more] + [j] + [self.feet_contact]), -5, +5)

	def calc_potential(self):
		# progress in potential field is speed*dt, typical speed is about 2-3 meter per second, this potential will change 2-3 per frame (not per second),
		# all rewards have rew/frame units and close to 1.0
		debugmode=0
		if (debugmode):
			print("calc_potential: self.walk_target_dist")
			print(self.walk_target_dist)
			print("self.scene.dt")
			print(self.scene.dt)
			print("self.scene.frame_skip")
			print(self.scene.frame_skip)
			print("self.scene.timestep")
			print(self.scene.timestep)
		return - self.walk_target_dist / self.scene.dt


class Hopper(WalkerBase):
	foot_list = ["foot"]

	def __init__(self):
		WalkerBase.__init__(self, "hopper.xml", "torso", action_dim=3, obs_dim=15, power=0.75)

	def alive_bonus(self, z, pitch):
		return +1 if z > 0.8 and abs(pitch) < 1.0 else -1


class Walker2D(WalkerBase):
	foot_list = ["foot", "foot_left"]

	def __init__(self):
		WalkerBase.__init__(self, "walker2d.xml", "torso", action_dim=6, obs_dim=22, power=0.40)

	def alive_bonus(self, z, pitch):
		return +1 if z > 0.8 and abs(pitch) < 1.0 else -1

	def robot_specific_reset(self):
		WalkerBase.robot_specific_reset(self)
		for n in ["foot_joint", "foot_left_joint"]:
			self.jdict[n].power_coef = 30.0


class HalfCheetah(WalkerBase):
	foot_list = ["ffoot", "fshin", "fthigh",  "bfoot", "bshin", "bthigh"]  # track these contacts with ground

	def __init__(self):
		WalkerBase.__init__(self, "half_cheetah.xml", "torso", action_dim=6, obs_dim=26, power=0.90)

	def alive_bonus(self, z, pitch):
		# Use contact other than feet to terminate episode: due to a lot of strange walks using knees
		return +1 if np.abs(pitch) < 1.0 and not self.feet_contact[1] and not self.feet_contact[2] and not self.feet_contact[4] and not self.feet_contact[5] else -1

	def robot_specific_reset(self):
		WalkerBase.robot_specific_reset(self)
		self.jdict["bthigh"].power_coef = 120.0
		self.jdict["bshin"].power_coef  = 90.0
		self.jdict["bfoot"].power_coef  = 60.0
		self.jdict["fthigh"].power_coef = 140.0
		self.jdict["fshin"].power_coef  = 60.0
		self.jdict["ffoot"].power_coef  = 30.0


class Ant(WalkerBase):
	foot_list = ['front_left_foot', 'front_right_foot', 'left_back_foot', 'right_back_foot']

	def __init__(self):
		WalkerBase.__init__(self, "ant.xml", "torso", action_dim=8, obs_dim=28, power=2.5)

	def alive_bonus(self, z, pitch):
		return +1 if z > 0.26 else -1  # 0.25 is central sphere rad, die if it scrapes the ground


class Humanoid(WalkerBase):
	self_collision = True
	foot_list = ["right_foot", "left_foot"]  # "left_hand", "right_hand"

	def __init__(self):
		WalkerBase.__init__(self, 'humanoid.xml', 'torso', action_dim=17, obs_dim=44, power=0.41)
		# 17 joints, 4 of them important for walking (hip, knee), others may as well be turned off, 17/4 = 4.25


	def robot_specific_reset(self):
		WalkerBase.robot_specific_reset(self)

		humanoidId = -1
		numBodies = p.getNumBodies()
		for i in range (numBodies):
		    bodyInfo = p.getBodyInfo(i)
		    if bodyInfo[1] == 'humanoid':
		        humanoidId = i
		## Spherical radiance/glass shield to protect the robot's camera
		glass_id = p.loadMJCF(os.path.join(self.physics_model_dir, "glass.xml"))
		print("setting up glass", glass_id, humanoidId)
		p.changeVisualShape(glass_id[0], -1, rgbaColor=[0, 0, 0, 0])
		#cid = p.createConstraint(humanoidId, -1, glass_id[0],-1,p.JOINT_FIXED,[0,0,0],[0,0,1.4],[0,0,1])

		self.motor_names  = ["abdomen_z", "abdomen_y", "abdomen_x"]
		self.motor_power  = [100, 100, 100]
		self.motor_names += ["right_hip_x", "right_hip_z", "right_hip_y", "right_knee"]
		self.motor_power += [100, 100, 300, 200]
		self.motor_names += ["left_hip_x", "left_hip_z", "left_hip_y", "left_knee"]
		self.motor_power += [100, 100, 300, 200]
		self.motor_names += ["right_shoulder1", "right_shoulder2", "right_elbow"]
		self.motor_power += [75, 75, 75]
		self.motor_names += ["left_shoulder1", "left_shoulder2", "left_elbow"]
		self.motor_power += [75, 75, 75]
		self.motors = [self.jdict[n] for n in self.motor_names]
		if self.random_yaw:
			position = [0,0,0]
			orientation = [0,0,0]
			yaw = self.np_random.uniform(low=-3.14, high=3.14)
			if self.random_lean and self.np_random.randint(2)==0:
				cpose.set_xyz(0, 0, 1.4)
				if self.np_random.randint(2)==0:
					pitch = np.pi/2
					position = [0, 0, 0.45]
				else:
					pitch = np.pi*3/2
					position = [0, 0, 0.25]
				roll = 0
				orientation = [roll, pitch, yaw]
			else:
				position = [0, 0, 1.4]
				orientation = [0, 0, yaw]  # just face random direction, but stay straight otherwise
			self.robot_body.reset_position(position)
			self.robot_body.reset_orientation(quatWXYZ2quatXYZW(euler2quat(orientation)))
		self.initial_z = 0.8

		orientation, position = get_model_initial_pose("humanoid")
		roll  = orientation[0]
		pitch = orientation[1]
		yaw   = orientation[2]
		self.robot_body.reset_orientation(quatWXYZ2quatXYZW(euler2quat(roll, pitch, yaw)))
		self.robot_body.reset_position(position)

		## BbxejD15Etk


	random_yaw = False
	random_lean = False

	def apply_action(self, a):
		assert( np.isfinite(a).all() )
		force_gain = 1
		for i, m, power in zip(range(17), self.motors, self.motor_power):
			m.set_motor_torque( float(force_gain * power*self.power*a[i]) )
			#m.set_motor_torque(float(force_gain * power * self.power * np.clip(a[i], -1, +1)))

	def alive_bonus(self, z, pitch):
		return +2 if z > 0.78 else -1   # 2 here because 17 joints produce a lot of electricity cost just from policy noise, living must be better than dying



class Husky(WalkerBase):
	foot_list = ['front_left_wheel_link', 'front_right_wheel_link', 'rear_left_wheel_link', 'rear_right_wheel_link']

	def __init__(self):
		WalkerBase.__init__(self, "husky.urdf", "husky_robot", action_dim=10, obs_dim=32, power=2.5)

	def alive_bonus(self, z, pitch):
		return +1 if z > 0.26 else -1  # 0.25 is central sphere rad, die if it scrapes the ground
