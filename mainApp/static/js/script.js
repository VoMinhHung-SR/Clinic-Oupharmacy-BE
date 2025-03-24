
function revenue_stats(option){

    event.preventDefault()
    document.getElementById("title_stats").innerText = "";
    document.getElementById("total_book_tour_stats").innerText = "" ;
    document.getElementById("total_bill_paid_stats").innerText = "";
    document.getElementById("total_revenue_stats").innerText = ""
    switch(option) {
          case 1:
            revenue_stats_month = document.getElementById("revenue_stats_month").value;
            var post_data = {
                "revenue_stats_month": revenue_stats_month
            };
            var fetch_url = '/revenue_stats/month/';
            break;
          case 2:
            revenue_stats_year = document.getElementById("revenue_stats_year").value;
            var post_data = {
                "revenue_stats_year": revenue_stats_year
            };
            var fetch_url = '/revenue_stats/year/';
            break;
          case 3:
            revenue_stats_from = document.getElementById("revenue_stats_from").value;
            revenue_stats_to = document.getElementById("revenue_stats_to").value;
            var post_data = {
                "revenue_stats_from": revenue_stats_from,
                "revenue_stats_to": revenue_stats_to
            };
            var fetch_url = '/revenue_stats/quarterly/';
            break;
        }
   fetch( fetch_url , {
        method: 'post',
        body: JSON.stringify(post_data),
        headers: {
            'Content-Type': 'application/json'
        }
    }).then(function(res) {
        return res.json()
    }).then(function(data) {
            switch(option) {
              case 1:
                document.getElementById("total_book_tour_stats").innerText = "Tổng số tour được đặt trong tháng là: " + data.count_book_tour ;
                document.getElementById("title_stats").innerText = "Thống kê theo tháng " + revenue_stats_month;
                document.getElementById("total_bill_paid_stats").innerText = "Số hóa đơn đã thanh toán: " + data.count_bill_paid;
                document.getElementById("total_revenue_stats").innerText = "Tổng doanh thu: " +
                (data.total_revenue).toLocaleString('en-US', {
                                                      style: 'currency',
                                                      currency: 'VND',
                                                    });
                break;
              case 2:
                document.getElementById("total_book_tour_stats").innerText = "Tổng số tour được đặt trong năm là: " + data.count_book_tour ;
                document.getElementById("title_stats").innerText = "Thống kê theo năm " + revenue_stats_year;
                document.getElementById("total_bill_paid_stats").innerText = "Số hóa đơn đã thanh toán: " + data.count_bill_paid;
                document.getElementById("total_revenue_stats").innerText = "Tổng doanh thu: " +
                            (data.total_revenue).toLocaleString('en-US', {
                                                                  style: 'currency',
                                                                  currency: 'VND',
                                                                });
                break;
              case 3:
                document.getElementById("total_book_tour_stats").innerText = "Tổng số tour được đặt trong quý là: " + data.count_book_tour ;
                document.getElementById("title_stats").innerText = "Thống kê theo quý " + revenue_stats_from +" đến "+ revenue_stats_to;
                document.getElementById("total_bill_paid_stats").innerText = "Số hóa đơn đã thanh toán: " + data.count_bill_paid;
                document.getElementById("total_revenue_stats").innerText = "Tổng doanh thu: " +
                            (data.total_revenue).toLocaleString('en-US', {
                                                                  style: 'currency',
                                                                  currency: 'VND',
                                                                });
                break;
            }
    }).catch(function(err){
    })
}
