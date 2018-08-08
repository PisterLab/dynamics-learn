import math
from dynamics import *
import pickle
from controllers import randController, MPController
from dynamics_ionocraft import IonoCraft
# from dynamics_ionocraft_imu import IonoCraft_IMU
# from dynamics_ionocraft_threeinput import IonoCraft_3u
from dynamics_crazyflie_linearized import CrazyFlie
from utils_plot import *
from utils_data import *
from models import LeastSquares
#from model_pnn import PNeuralNet
from model_general_nn import GeneralNN, predict_nn
import torch
from torch.nn import MSELoss
# import torch.nn as nn
import time
import datetime

# Plotting
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

from enum import Enum


class RunType(Enum):
  CF   = 1
  IONO = 2

runType = RunType.CF



data_name  = 'green'

using_premade_data = False
old_model = False




### EXAMPLE EXECUTION

################################ INITIALIZATION ################################
print('\n')
print('---begin--------------------------------------------------------------')
start_time = time.time()
# initialize some variables
dt_x = .0002        # 5khz dynam update
dt_m = .002         # 500 hz measurement update
dt_u = .004         # ~200 hz control update
samp = int(dt_m/dt_x)     # effective sample rate of simulated data

print('Simulation update step is: ', dt_x, ' and control update is: ', dt_u, 'the ratio is: ', dt_u/dt_x)

print('...Initializing Dynamics Object')
# dynamics object
if runType is RunType.IONO:
	iono1 = IonoCraft(dt_x, threeinput = True, x_noise = 1e-9)   #use from dynamics_ionocraft.py
	# initial state is origin
	x0 = np.zeros(iono1.x_dim)
	u0 = iono1.u_e

	# good for unit testin dynamics
	x1 = iono1.simulate(x0,u0)
	printState(x1)

elif runType is RunType.CF:
	crazy1 = CrazyFlie(dt_x, x_noise = .000)
	# initial state is origin
	x0 = np.zeros(crazy1.x_dim)
	u0 = crazy1.u_e

	# good for unit testin dynamics
	x1 = crazy1.simulate(x0,u0)
	printState(x1)

# quit()

################################ DATA ################################
# Simulate data for training
N = 150     # num sequneces


# generate training data
print('...Generating Training Data')
# Seqs_X, Seqs_U = generate_data(iono1, dt_m, dt_control = dt_u, sequence_len=200, num_iter = N, variance = .007)
if runType is RunType.IONO:
  Seqs_X, Seqs_U = loadcsv('_logged_data/iono/tt_log_4.csv')
elif runType is RunType.CF:
  #Seqs_X, Seqs_U = loadcsv('_logged_data/crazyflie/stateandaction-20180711T22-44-47.csv')
  #Seqs_X, Seqs_U = loadcsv('_logged_data/crazyflie/stateandaction-20180717T20-53-44.csv')
  #Seqs_X, Seqs_U = loadcsv('_logged_data/crazyflie/clean_fly_and_hover_long_data.csv')
  #Seqs_X, Seqs_U = loadcsv('_logged_data/crazyflie/hopping.csv')
  Seqs_X, Seqs_U = loadcsv('_logged_data/crazyflie/' + data_name + '.csv')
  data = np.concatenate([Seqs_X,Seqs_U],1)
  data = data[data[:,3]!=0,:]
  print("Original data: ", data.shape)
  states = np.concatenate([data[:,1:3],data[:,4:6],data[:,7:8]], 1)
  #states = np.concatenate([data[:,4:6],data[:,7:8]], 1)
  print("Linear: ", states[:,1])
  print("Angular: ", states[:,0])
  imu = unpack_cf_imu(states[:,1], states[:,0]) # linear and angular acceleration

  Seqs_X = np.concatenate([imu[:,3:], states[:,3:5]], 1)
  #Seqs_X = np.concatenate([imu, states[:,2:]], 1)
  #Seqs_X = np.concatenate([imu, states], 1) # linear accel, angular accel, and YPR
  #Seqs_X = states # YPR ONLY
  Seqs_U = unpack_cf_pwm(data[:,3])
  #print(np.shape(Seqs_U))
  print(np.mean(Seqs_U,axis=0))


if len(Seqs_X.shape) < 3:
  print("added padding dimension to Seqs_X")
  Seqs_X = np.expand_dims(Seqs_X, axis=0)
if len(Seqs_U.shape) < 3:
  print("added padding dimension to Seqs_U")
  Seqs_U = np.expand_dims(Seqs_U, axis=0)


print("Data : \n", Seqs_X, Seqs_U)
np.savez('_simmed_data/testingfile_generalnn.npz', Seqs_X, Seqs_U)

print('.... loading training data')
npzfile = np.load('_simmed_data/testingfile_generalnn.npz')
Seqs_X = npzfile['arr_0']
Seqs_U = npzfile['arr_1']


# converts data from list of trajectories of [next_states, states, inputs] to a large array of [next_states, states, inputs]
# downsamples by a factor of samp. This is normalizing the differnece betweem dt_x and dt_measure
data = sequencesXU2array(Seqs_X, Seqs_U)


################################ LEARNING ################################



width = 100
epochs = 75
batch  = 32
learning_rate = 9e-7
prob = True



"""
# #creating neural network with 2 layers of 100 linearly connected ReLU units
print('...Training Model')
layer_sizes = [12, 400, 400, 9]
layer_types = ['nn.Linear()','nn.ReLU()', 'nn.Linear()', 'nn.Linear()']
states_learn = ['yaw', 'pitch', 'roll', 'ax', 'ay', 'az'] #,'ax', 'ay', 'az'] #['yaw', 'pitch', 'roll', 'ax', 'ay', 'az']
# ['X', 'Y', 'Z', 'vx', 'vy', 'vz', 'yaw', 'pitch', 'roll', 'w_z', 'w_x', 'w_y']
forces_learn = ['Thrust', 'taux', 'tauy']



if runType is RunType.CF:
  newNN = GeneralNN(n_in_input = 4, n_in_state = 4, hidden_w=width, n_out = 4, state_idx_l=[0,1,2,3], prob=prob, pred_mode = 'Next State')#, ang_trans_idx =[0,1,2])
elif runType is RunType.IONO:
  #newNN = GeneralNN(n_in_input = 4, n_in_state = 6, n_out = 6, state_idx_l=[0,1,2,3,4,5], prob=False, pred_mode = 'Next State')#, ang_trans_idx =[0,1,2])
  newNN = GeneralNN(n_in_input = 4, n_in_state = 6, n_out = 6, state_idx_l=[0,1,2,3,4,5], prob=True, pred_mode = 'Next State')#, ang_trans_idx =[0,1,2])
else:
  newNN = GeneralNN(n_in_input = 3, n_in_state = 3, n_out = 3, state_idx_l=[6,7,8], prob=True, pred_mode = 'Next State')#, ang_trans_idx =[0,1,2])
ypraccel = [6,7,8,12,13,14]
ypr = [6,7,8]
print(np.shape(Seqs_U))

if not using_premade_data:
  np.savetxt('_logged_data/crazyflie/' + data_name + '-Seqs_X.csv', Seqs_X[0], delimiter=',')
  np.savetxt('_logged_data/crazyflie/' + data_name + '-Seqs_U.csv', Seqs_U[0], delimiter=',')

if using_premade_data:
  Seqs_X = np.loadtxt(open('_logged_data/crazyflie/' + data_name + '-Seqs_X-new5.csv', 'r', encoding='utf-8'), delimiter=",", skiprows=1)
  Seqs_U = np.loadtxt(open('_logged_data/crazyflie/' + data_name + '-Seqs_U-new.csv', 'r', encoding='utf-8'), delimiter=",", skiprows=1)
  data = np.concatenate([Seqs_X,Seqs_U],1)
  Seqs_X = np.expand_dims(Seqs_X, axis=0)
  Seqs_U = np.expand_dims(Seqs_U, axis=0)
  data = sequencesXU2array(Seqs_X, Seqs_U)

#dim0, dim1 = Seqs_X.shape

#noiseX = 0.7 * np.random.rand(dim0, dim1)

#Seqs_X = Seqs_X + noiseX

"""






def eval(model, dims = [0,1,2,3,4]):
  SE = [0]*len(dims)
  for i in range(0, len(data) - 1):
    predictions = predict_nn(model, data[i][1], data[i][2], [0,1,2,3,4])
    for j,prediction in enumerate(predictions):
      SE[j] += (data[i+1][1][j] - prediction) ** 2
      
  MSE = [0]*len(dims)
  for i,error in enumerate(SE):
    MSE[i] = error / (len(data) - 1)
    
  return MSE










def run(model, learning_rate, epochs, epoch_step, batch, width, depth, threshold = -0.1):
  newNN = model
  if epoch_step < 2:
    print("PARAMETER ERROR! epoch_step must be >= 2")
    quit()
  
  if runType is RunType.CF:
    if not old_model:
      for i in range(0, epochs+1, epoch_step):
        acc = newNN.train((Seqs_X, Seqs_U), learning_rate=learning_rate, epochs=epoch_step, batch_size = batch, optim="Adam")
        if (acc[-1] - acc[-2]) > threshold:
          return
        else:
          last_loss = acc
        dir_str = str('_models/sweep/')
        date_str = str(datetime.datetime.now())
        info_str = "w-" + str(width) + "_d-" + str(depth) + "_e-" + str(i+epoch_step) + "_lr-" + str(learning_rate) + "_b-" + str(batch) + "_ds-" + str(data_name) + "_p-" + str(prob)
        model_name = dir_str + info_str
        newNN.save_model(model_name + '.pth')
        print("Saved: ", model_name)
        
    print("Done.")
  elif runType is RunType.IONO:
    acc = newNN.train((Seqs_X, Seqs_U), learning_rate=2.5e-5, epochs=50, batch_size = 100, optim="Adam")
  else:
    acc = newNN.train((Seqs_X[:,::samp,ypr], Seqs_U[:,::samp,:]), learning_rate=2.5e-5, epochs=25, batch_size = 100, optim="Adam")


  # Save normalizing parameters




  # Saves model with date string for sorting
  #dir_str = str('_models/')
  #date_str = str(datetime.datetime.now())
  #info_str = "w-" + str(width) + "e-" + str(epochs) + "lr-" + str(learning_rate) + "b-" + str(batch) + "d-" + str(data_name) + "p-" + str(prob)
  model_name = dir_str + date_str + info_str
  newNN.save_model(model_name + '.pth')
  
  
  
  info_str = "w-" + str(width) + "_d-" + str(depth) + "_e-" + str(epochs) + "_lr-" + str(learning_rate) + "_b-" + str(batch) + "_ds-" + str(data_name) + "_p-" + str(prob)
  model_name = dir_str + info_str
  normX, normU, normdX = newNN.getNormScalers()

  with open(model_name+"-normparams.pkl", 'wb') as pickle_file:
    pickle.dump((normX,normU,normdX), pickle_file, protocol=2)
  time.sleep(1)

  #print('Loading as new model')
  #if old_model:
  #  newNN = torch.load('_models/model.pth')
  #if runType is RunType.CF:
    #acc2 = newNN2.train((Seqs_X, Seqs_U), learning_rate=2.5e-5, epochs=25, batch_size = 100, optim="Adam")
  #else:
  #  acc = newNN.train((Seqs_X[:,::samp,ypr], Seqs_U[:,::samp,:]), learning_rate=2.5e-5, epochs=25, batch_size = 100, optim="Adam")

  # Plot accuracy #
  #plt.plot(np.transpose(acc2))
  #if not old_model:
  #  plt.plot(np.transpose(acc))
  #  plt.show()
#quit()

# quit()
#
# pnn = PNeuralNet()
# pnn_ypr = PNeuralNet_ypr()
# dnn_ypr = NeuralNet_ypr()
# # ['F1', 'F2', 'F3', 'F4']
# # nn = NeuralNet(layer_sizes, layer_types, iono1, states_learn, forces_learn)
#
#
# ypraccel = [6,7,8,12,13,14]
# ypr = [6,7,8]
# # Create New model
# # acc = nn_ens.train_ens((Seqs_X[:,::samp,:], Seqs_U[:,::samp,:]), learning_rate=2.5e-5, epochs=15, batch_size = 1500, optim="Adam")
# # acc = pnn.train((Seqs_X[:,::samp,ypraccel], Seqs_U[:,::samp,:]), learning_rate=7.5e-6, epochs=240, batch_size = 100, optim="Adam")
#
# acc = pnn_ypr.train((Seqs_X[:,::samp,ypr], Seqs_U[:,::samp,:]), learning_rate=2.5e-5, epochs=200, batch_size = 100, optim="Adam")
#
# # Plot accuracy #
#plt.plot(np.transpose(acc))
#plt.show()

# Saves model with date string for sorting
# dir_str = str('_models/')
# date_str = str(datetime.date.today())
# model_name = str('_MODEL_absdet')
# pnn.save_model(dir_str+date_str+model_name+'.pth')

# Or load model
# pnn = torch.load('pnn_moredata.pth')
#newNN = torch.load(dir_str+'greatmodel-2.pth')
print(np.shape(data))
toPlot1 = []
toPlot2 = []
toPlot3 = []

for i in data:
  toPlot1.append(i[0])
  toPlot2.append(i[1])
  toPlot3.append(i[2])
#plt.plot(toPlot1)
#plt.show()
#plt.plot(toPlot2)
#plt.show()
#plt.plot(toPlot3)
#plt.show()

ypr = [0,1,2,3]

plt.show()




#plot_model(data, newNN, 0, model_dims = ypr, delta=True)
#plot_model(data, newNN, 1, model_dims = ypr, delta=True)
#plot_model(data, newNN, 2, model_dims = ypr, delta=True)
#plot_model(data, newNN, 3, model_dims = ypr, delta=True)
#plot_model(data, newNN, 4, model_dims = ypr, delta=True)

#plot_model(data, newNN, 0, model_dims = ypr, delta=False)
#plot_model(data, newNN, 1, model_dims = ypr, delta=False)
#plot_model(data, newNN, 2, model_dims = ypr, delta=False)
#plot_model(data, newNN, 3, model_dims = ypr, delta=False)
#plot_model(data, newNN, 4, model_dims = ypr, delta=False)
#plt.show()
#plot_trajectories_state(Seqs_X, 2)

#quit()
"""
################################ Obj Fnc ################################
origin_minimizer = Objective(np.linalg.norm, 'min', 3, dim_to_eval=[6,7,8])
print('...Objective Function Initialized')

################################ MPC ################################

# initialize MPC object with objective function above
if runType is RunType.CF:
	mpc1 = MPController(newNN, crazy1, dt_x, dt_u, origin_minimizer, N=40, T=5, variance = 100) #.00003
elif runType is RunType.IONO:
	mpc1 = MPController(newNN, iono1, dt_x, dt_u, origin_minimizer, N=40, T=5, variance = .00003)
print('...MPC Running')

new_len = 500
x_controlled, u_seq = sim_sequence(crazy1, dt_m, dt_u, controller = mpc1, sequence_len = new_len, to_print = True)


# x0 = np.zeros(12)
# new_seq, Us = sim_sequence(iono1, dt_u, sequence_len = 150, x0=x0, controller = mpc1)
#
# compareTraj(Us, x0, iono1, nn, show=True)
################################ Sim Controlled ################################

# Sim sequence off the trained controller
new_len = 5000
x_controlled, u_seq = sim_sequence(crazy1, dt_m, dt_u, controller = mpc1, sequence_len = new_len, to_print = False)
#print(np.mean(x_controlled[:,[12,13,14]]))
print(x_controlled[:,[6,7,8]])
print('Simulated Learned.')
################################ PLot ################################
print('...Plotting')
# plot states and inputs of the trajectory if wanted
T = np.linspace(0,new_len*dt_x,new_len)
plot12(x_controlled, T)
# plotInputs(u_seq, T)
fig_inputs = plt.figure()
plt.title('Three Inputs')
plt.plot(T, u_seq[:,0],label='PWM1')
plt.plot(T, u_seq[:,1],label='PWM2')
plt.plot(T, u_seq[:,2],label='PWM3')
plt.plot(T, u_seq[:,3],label='PWM4')
plt.legend()
# plt.show()
# # Plots animation, change save to false to not save .gif
plotter1 = PlotFlight(x_controlled[::15,:],.5)
plotter1.show(save=False)
# print('Saved Gif')


print('---------------------------------------------------------end run-----')
"""