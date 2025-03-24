var myCareerChart = undefined;


function cb() {
    if(myCareerChart)
        myCareerChart.destroy()

    const ctx2 = document.getElementById("chart-career-pie").getContext("2d");
    fetch('/admin/api/revenue_stats/', {
        method: 'GET', headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': Cookies.get('csrftoken'),
        }
    })
    .then(response => response.json())
    .then(data => {
         const revenue_chart = {
            datasets: [{
              data: data.data_revenue,
              borderColor: "#30747e", backgroundColor:"#1f3865",
              label: "Thống kê doanh thu theo các tháng trong năm 2023",
              borderWidth: 1,
            }],
            labels: [
              'Tháng 1',
              'Tháng 2',
              'Tháng 3',
              'Tháng 4',
              'Tháng 5',
              'Tháng 6',
              'Tháng 7',
              'Tháng 8',
              'Tháng 9',
              'Tháng 10',
              'Tháng 11',
              'Tháng 12'
            ]
          };

         var myCareerChart = new Chart(ctx2, {
            type: 'line',
            data: revenue_chart,
            options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                          boxWidth: 30
                    }
                }
            }
        },
        });
    });


}

cb();

