from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from rent.models.lease import LesseeData, Contract, Lease, Payment, Due
from users.models import Associated
from rent.forms.lease import PaymentForm
from django.db import transaction
from datetime import timedelta, datetime
from django.utils import timezone
import pytz
from django.conf import settings


def compute_client_debt(client: Associated, lease: Lease):
    interval_start = get_start_paying_date(client, lease)
    unpaid_dues = len(lease.event.get_occurrences(interval_start,
                                                  timezone.now()))
    return unpaid_dues*lease.payment_amount, interval_start


@login_required
def client_list(request):
    # Create leases if needed
    contracts = Contract.objects.exclude(stage="ended")
    clients = []
    payment_dates = {}
    n_active = 0
    n_processing = 0
    for contract in contracts:
        client = contract.lessee
        clients.append(client)
        client.trailer = contract.trailer
        client.contract = contract
        payment_dates.setdefault(client.id, timezone.now())
        if contract.stage == "active":
            n_active += 1
            try:
                lease = Lease.objects.get(contract=contract)
            except Lease.DoesNotExist:
                lease = Lease.objects.create(
                    contract=contract,
                    payment_amount=contract.payment_amount,
                    payment_frequency=contract.payment_frequency,
                    event=None,
                )
            client.debt, last_payment = compute_client_debt(
                client, lease)
            client.last_payment = last_payment
            payment_dates[client.id] = last_payment
        else:
            n_processing += 1

    sorted_clients = sorted(
        clients, key=lambda client: payment_dates[client.id])
    print(sorted_clients)
    context = {
        "clients": sorted_clients,
        "n_active": n_active,
        "n_processing": n_processing,
    }

    return render(request, "rent/client/client_list.html", context=context)


@login_required
def client_detail(request, id):
    # Create leases if needed
    client = get_object_or_404(Associated, id=id)
    client.contract = Contract.objects.filter(stage="active").last()
    client.data = LesseeData.objects.get(associated=client)
    context = {
        "client": client,
    }

    return render(request, "rent/client/client_detail.html", context=context)


def get_start_paying_date(client: Associated, lease: Lease):
    # Find the last due payed by the client
    last_due = Due.objects.filter(client=client, lease=lease).last()
    if last_due is not None:
        interval_start = last_due.date
    else:
        # If the client hasn't paid, then start on effective date
        interval_start = lease.contract.effective_date
    # Make it timezone aware
    interval_start = timezone.make_aware(datetime.combine(
        interval_start, datetime.min.time()), pytz.timezone(settings.TIME_ZONE))
    return interval_start


def process_payment(payment: Payment):
    # Init the payment remaining
    payment.remaining = payment.amount

    # Get the remaining money from last payment
    last_payment = Payment.objects.filter(client=payment.client,
                                          lease=payment.lease).last()
    if last_payment is not None:
        payment.remaining += last_payment.remaining
        last_payment.remaining = 0
        last_payment.save()

    # Create as many dues as possible
    interval_start = get_start_paying_date(payment.client, payment.lease)

    # Get occurrences from the last due payed
    occurrences = payment.lease.event.occurrences_after(interval_start)

    while payment.remaining >= payment.lease.payment_amount:
        payment.remaining -= payment.lease.payment_amount
        Due.objects.create(
            date=next(occurrences).start.date(),
            amount=payment.lease.payment_amount,
            client=payment.client,
            lease=payment.lease
        )


@login_required
@transaction.atomic
def payment(request, client_id):
    client = get_object_or_404(Associated, id=client_id)
    try:
        lease = Lease.objects.get(
            contract__lessee=client, contract__stage='active')
    except Lease.DoesNotExist:
        raise Exception("No active lease found for the client")

    if request.method == 'POST':
        form = PaymentForm(request.POST, client=client)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.client = client
            payment.user = request.user
            process_payment(payment)
            payment.save()
            # Redirect to a success page
            return redirect('client-detail', client.id)
    else:
        form = PaymentForm(client=client)

    context = {
        'form': form,
        'client': client,
        'title': "Rental payment"
    }
    return render(request, 'rent/client/payment.html', context)
