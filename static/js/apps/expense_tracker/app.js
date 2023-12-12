// Define the `expenseTrackerApp` module
var expenseTrackerApp = angular.module('expenseTrackerApp', ['720kb.datepicker']);

// Define the `ExpenseTrackerController` controller on the `expenseTrackerApp` module
expenseTrackerApp.controller('ExpenseTrackerController', function ExpenseTrackerController($scope, $http) {
  $scope.search_data = {};

  $http.get('/expensetracker/api/v1/laundry-rooms').then(function(response) {
    $scope.laundry_rooms = response.data;
  });

  $http.get('/expensetracker/api/v1/machines').then(function(response) {
    $scope.machines = response.data;
  });
  
  $http.get('/expensetracker/api/v1/technicians').then(function(response) {
    $scope.technicians = response.data;
  });

  $http.get('/expensetracker/api/v1/job-statuses').then(function(response) {
    $scope.statuses = response.data;
  });

  $http.get('/expensetracker/api/v1/job-types').then(function(response) {
    $scope.types = response.data;
  });

  $http.get('/expensetracker/api/v1/line-item-types').then(function(response) {
    $scope.line_item_types = response.data;
  });

  $http.get('/expensetracker/api/v1/line-item-statuses').then(function(response) {
    $scope.line_item_statuses = response.data;
  });

  $scope.result = [];
  $scope.search = function() {
    $http.post('/expensetracker/api/v1/search', $scope.search_data).then(function(response) {
      $scope.result = response.data;
    });
  }

  $scope.toggleShowLineItems = function(job) {
    if (job.show_line_items) job.show_line_items = false;
    else job.show_line_items = true;
  }

  $scope.toggleShowNewJobForm = function() {
    if ($scope.show_new_job_form) $scope.show_new_job_form = false;
    else $scope.show_new_job_form = true;
  }

  $scope.toggleShowNewLineItemForm = function(job) {
    if (job.show_new_line_item_form) job.show_new_line_item_form = false;
    else job.show_new_line_item_form = true;
  }

  $scope.resetSavedMessage = function() {
    $scope.errors = null;
    $scope.successful_save_job = null;
    $scope.error_save_job = null;
    $scope.successful_save_line_item = null;
    $scope.error_save_line_item = null;
    $scope.new_job_sucess = null;
    $scope.new_job_errors = null;
    $scope.new_line_item_sucess = null;
    $scope.new_line_item_errors = null;
  }

  $scope.saveJob = function(job) {
    $scope.resetSavedMessage();
    if(!job.start_date) {
      job.start_date = null;
    }
    if(!job.final_date) {
      job.final_date = null;
    }
    
    $http.put('/expensetracker/api/v1/jobs/' + job.id, job).then(
      function(response) {
        $scope.successful_save_job = job;
      },
      function(response) {
        $scope.error_save_job = job;
        $scope.errors = response.data;
      });
  }

  $scope.saveNewJob = function(job) {
    $scope.resetSavedMessage();
    if(!job.laundry_room) {
      job.laundry_room = null;
    }
    if(!job.machine) {
      job.machine = null;
    }
    if(!job.start_date) {
      job.start_date = null;
    }
    if(!job.final_date) {
      job.final_date = null;
    }
    $http.post('/expensetracker/api/v1/jobs', job).then(
      function(response) {
        $scope.result.push(response.data);
        job = {};
        $scope.new_job_sucess = true;
      },
      function(response) {
        $scope.new_job_errors = response.data;
      });
  }

  $scope.saveLineItem = function(line_item) {
    $scope.resetSavedMessage();
    if (!line_item.start_date) {
      line_item.start_date = null;
    }
    if (!line_item.finish_date) {
      line_item.finish_date = null;
    }
    
    $http.put('/expensetracker/api/v1/line_items/' + line_item.id, line_item).then(
      function(response) {
        $scope.successful_save_line_item = line_item;
        line_item.cost = response.data.cost;
      },
      function(response) {
        $scope.error_save_line_item = line_item;
        $scope.errors = response.data;
      });
  }

  $scope.saveNewLineItem = function(line_item, job) {
    $scope.resetSavedMessage();
    line_item.job = job.id;
    if (!line_item.technician) {
      line_item.technician = null;
    }
    if (!line_item.start_date) {
      line_item.start_date = null;
    }
    if (!line_item.finish_date) {
      line_item.finish_date = null;
    }
    if (!line_item.time) {
      line_item.time = null;
    }
    if (!line_item.cost) {
      line_item.cost = null;
    }
    $http.post('/expensetracker/api/v1/line_items', line_item).then(
      function(response) {
        job.line_items.push(response.data);
        line_item = {};
        $scope.new_line_item_sucess = true;
      },
      function(response) {
        $scope.new_line_item_errors = response.data;
      });
  }

  $scope.checkEmployee = function(line_item) {
    if (line_item.line_item_type == 'LABOR') {
      for (var i = 0; i < $scope.technicians.length; i++) {
        if ($scope.technicians[i].id == line_item.technician) {
          if ($scope.technicians[i].employment_type == 'EMPLOYEE') {
            return true;
          }
          return false;
        }
      }
      return false;
    }
    return false;
  }
});