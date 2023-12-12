#testing the arithmetic of the landlord guaranteed minimum compensation difference
#Now first we define the variables and the logic


#If net revenue < lgmc_number:
#Landlord pays difference:
#lgmc_num - net_revenue
#Right?
#If there’s not enough net revenue to pay us the guaranteed minimum, landlord has to come out of their pocket to make up that difference
#lgmc_num = lgmc_percentage * min_comp


#The variables are:
#1 net revenue (already calculated)
#2 Minimum Compensation (alread calculated)

#Cases 

def landlord_pays_calculation(net_revenue, minimum_compensation, landlord_guarantee_percent):
    landlord_guarantee = landlord_guarantee_percent * minimum_compensation

    # If the minimum compensation is greater than net revenue
    if net_revenue < landlord_guarantee:
        landlord_owes_aces = landlord_guarantee - net_revenue
        print(f'Landlord pays the difference: {landlord_owes_aces}')
        return landlord_guarantee
    else:
        print('No payment required from the landlord.')
        return 0

# Save the landlord guarantee variable by calling the function
net_revenue = 0  # Replace with the actual net revenue value
minimum_compensation = 1000  # Replace with the actual minimum compensation value
landlord_guarantee_percent = 0.1  # Replace with the actual percentage

lg = landlord_pays_calculation(net_revenue, minimum_compensation, landlord_guarantee_percent)


def calc_landlord_owes(landlord_guarantee, net_revenue):
    landlord_owes = landlord_guarantee - net_revenue

    if 0 <= landlord_owes <= 1:  # Using the recommended range
        return landlord_owes
    else:
        return 0

# Example usage
net_revenue = 500  # Replace with the actual net revenue value
landlord_guarantee = lg  # Use the previously calculated landlord guarantee
landlord_owes_amount = calc_landlord_owes(landlord_guarantee, net_revenue)

print(f'Landlord owes: {landlord_owes_amount}')