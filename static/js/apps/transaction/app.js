// Define the `transactionApp` module
var transactionApp = angular.module('transactionApp', ['720kb.datepicker']);

// Define the `TransactionController` controller on the `transactionApp` module
transactionApp.controller('TransactionController', function TransactionController($scope, $http) {
  $scope.search_data = {};

  $http.get('/roommanager/api/v1/laundry-rooms').then(function(response) {
    $scope.laundry_rooms = response.data;
  });

  $http.get('/roommanager/api/v1/machines').then(function(response) {
    $scope.machines = response.data;
  });
  
  $http.get('/roommanager/api/v1/slots').then(function(response) {
    $scope.slots = response.data;
  });

  $http.get('/revenue/api/v1/payment-types').then(function(response) {
    $scope.payment_types = response.data;
  });

  $http.get('/revenue/api/v1/activity-types').then(function(response) {
    $scope.activity_types = response.data;
  });

  $scope.result = [];
  $scope.search = function() {
	console.log("point a")
    if ($scope.search_data.date && $scope.search_data.time) {
      $scope.search_data.start_time = $scope.search_data.date + ' ' + $scope.search_data.time + ':00';
    }

    $http.post('/revenue/api/v1/search', $scope.search_data).then(function(response) {
      $scope.result = response.data;
    },
    function(response) {
      $scope.errors = response.data;
    });
  };

  $scope.selected_transactions = [];
  $scope.toggleSelectTransaction = function(transaction) {
    var idx = $scope.selected_transactions.indexOf(transaction);

    if (idx > -1) {
      $scope.selected_transactions.splice(idx, 1);
    } else {
      $scope.selected_transactions.push(transaction);
    }
  };

  $scope.refund = function() {
    $scope.has_error = null;
    $scope.success = null;
    $scope.errors = null;
    angular.forEach($scope.result, function(transaction) {
      transaction.refund_error = false;
    });

    $http.post('/revenue/api/v1/refund', {transactions: $scope.selected_transactions}).then(
      function(response) {
        $scope.success = true;
        if (response.data.has_error) {
          $scope.has_error = true;
        }
        $scope.errors = response.data.error_transactions;
        angular.forEach($scope.result, function(transaction) {
          var idx = $scope.selected_transactions.indexOf(transaction.id);

          if (idx > -1) {
            var index = $scope.errors.indexOf(transaction.id);
            if (index == -1)
              transaction.is_refunded = true;
            else {
              transaction.refund_error = true;
            }
          }
        });
      },
      function(response) {
        $scope.has_error = true;
      });
  }
});