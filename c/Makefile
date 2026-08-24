.DEFAULT_GOAL := all

CXX ?= c++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -O2
CC ?= cc
CFLAGS ?= -std=c11 -Wall -Wextra -pedantic -O2

ROOT_DIR := ..
INCLUDE_DIR := $(ROOT_DIR)/dist/include
CPP_INCLUDE_DIR := $(INCLUDE_DIR)
BUILD_DIR := build

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
  LIB_DIR := $(ROOT_DIR)/dist/shared/mac
  SDK_LIB := $(LIB_DIR)/libbc_revo3_sdk.dylib
  RPATH := -Wl,-rpath,$(abspath $(LIB_DIR))
else ifeq ($(UNAME_S),Linux)
  LIB_DIR := $(ROOT_DIR)/dist/shared/linux
  SDK_LIB := $(LIB_DIR)/libbc_revo3_sdk.so
  RPATH := -Wl,-rpath,$(abspath $(LIB_DIR))
else
  LIB_DIR := $(ROOT_DIR)/dist/shared/win
  SDK_LIB := $(LIB_DIR)/bc_revo3_sdk.dll
  RPATH :=
endif

INCLUDES := -I$(CPP_INCLUDE_DIR) -I$(INCLUDE_DIR)
LDFLAGS := -L$(LIB_DIR) -lbc_revo3_sdk $(RPATH)

TARGETS := $(BUILD_DIR)/demo/quickstart $(BUILD_DIR)/demo/multi_hand $(BUILD_DIR)/demo/device_operations $(BUILD_DIR)/demo/firmware_update $(BUILD_DIR)/demo/touch_sensor $(BUILD_DIR)/demo/touch_hybrid $(BUILD_DIR)/demo/streaming_control $(BUILD_DIR)/demo/mit_plan $(BUILD_DIR)/demo/teaching_mode $(BUILD_DIR)/diagnostics/collision_detection

LEGACY_TARGETS := demo/auto_detect demo/hand_demo demo/hand_dfu demo/hand_trajectory demo/revo3_feedback_benchmark demo/revo3_manager_mit_plan demo/revo3_manager_multi_hand demo/revo3_manager_operations demo/revo3_manager_quickstart demo/revo3_manager_teaching demo/revo3_manager_touch demo/revo3_mit_plan demo/revo3_monitor demo/revo3_motor demo/revo3_ota_resource demo/revo3_servo demo/revo3_touch

all: $(TARGETS)

$(BUILD_DIR)/diagnostics/collision_detection: diagnostics/collision_detection.cpp $(CPP_INCLUDE_DIR)/revo3/revo3.hpp $(SDK_LIB)
	@mkdir -p $(@D)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< -o $@ $(LDFLAGS)

$(BUILD_DIR)/demo/quickstart: demo/quickstart.cpp $(CPP_INCLUDE_DIR)/revo3/revo3.hpp $(SDK_LIB)
	@mkdir -p $(@D)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< -o $@ $(LDFLAGS)

$(BUILD_DIR)/demo/multi_hand: demo/multi_hand.cpp $(CPP_INCLUDE_DIR)/revo3/revo3.hpp $(SDK_LIB)
	@mkdir -p $(@D)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< -o $@ $(LDFLAGS)

$(BUILD_DIR)/demo/device_operations: demo/device_operations.cpp $(CPP_INCLUDE_DIR)/revo3/revo3.hpp $(SDK_LIB)
	@mkdir -p $(@D)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< -o $@ $(LDFLAGS)

$(BUILD_DIR)/demo/firmware_update: demo/firmware_update.cpp $(CPP_INCLUDE_DIR)/revo3/revo3.hpp $(SDK_LIB)
	@mkdir -p $(@D)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< -o $@ $(LDFLAGS)

$(BUILD_DIR)/demo/touch_sensor: demo/touch_sensor.cpp $(CPP_INCLUDE_DIR)/revo3/revo3.hpp $(SDK_LIB)
	@mkdir -p $(@D)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< -o $@ $(LDFLAGS)

$(BUILD_DIR)/demo/touch_hybrid: demo/touch_hybrid.cpp $(CPP_INCLUDE_DIR)/revo3/revo3.hpp $(SDK_LIB)
	@mkdir -p $(@D)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< -o $@ $(LDFLAGS)

$(BUILD_DIR)/demo/streaming_control: demo/streaming_control.cpp $(CPP_INCLUDE_DIR)/revo3/revo3.hpp $(SDK_LIB)
	@mkdir -p $(@D)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< -o $@ $(LDFLAGS)

$(BUILD_DIR)/demo/mit_plan: demo/mit_plan.cpp $(CPP_INCLUDE_DIR)/revo3/revo3.hpp $(SDK_LIB)
	@mkdir -p $(@D)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< -o $@ $(LDFLAGS)

$(BUILD_DIR)/demo/teaching_mode: demo/teaching_mode.cpp $(CPP_INCLUDE_DIR)/revo3/revo3.hpp $(SDK_LIB)
	@mkdir -p $(@D)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $< -o $@ $(LDFLAGS)

$(SDK_LIB):
	@echo "Missing SDK library: $(SDK_LIB)"
	@echo "Run: bash download-lib.sh"
	@exit 1

clean:
	rm -rf $(BUILD_DIR)
	rm -f $(LEGACY_TARGETS)
	rm -rf demo/*.dSYM diagnostics/*.dSYM

help:
	@echo "Build all C++ Revo3 examples: make -C c"
	@echo "Run Revo3 Quickstart:        ./c/build/demo/quickstart [--port /dev/ttyUSB0] [--move]"
	@echo "Run Multi-Hand:              ./c/build/demo/multi_hand"
	@echo "Run Device Operations:       ./c/build/demo/device_operations [--calibrate|--reboot]"
	@echo "Run Firmware Update:         ./c/build/demo/firmware_update --firmware FILE [--target main|image|motor] --run"
	@echo "Run Touch Sensor:            ./c/build/demo/touch_sensor [--port /dev/ttyUSB0]"
	@echo "Run Hybrid Touch:            ./c/build/demo/touch_hybrid [port] [--test-tare]"
	@echo "Run Revo3 Streaming:         ./c/build/demo/streaming_control [port] --move"
	@echo "Run MIT Plan:                ./c/build/demo/mit_plan [port] --run"
	@echo "Run Teaching Mode:           ./c/build/demo/teaching_mode [port] --move"

.PHONY: all clean help
