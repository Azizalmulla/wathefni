# REFERENCE.md - Riders Facts

Static business facts for policy and FAQ answers. Live tool results override this file for prices, coverage, tracking, payment, and order state.

## About Riders

- Riders provides on-demand delivery drivers across Kuwait.
- No minimum order and no mandatory contract for normal delivery use.
- Customers can order through WhatsApp when the chat flow supports it, or through the website.
- Website: https://order.tryriders.com
- WhatsApp/contact number: 1880999

## Delivery Scope

Riders delivers prepared and prepaid items:

- home to home
- office to chalet
- store to customer
- supermarkets
- printing shops
- clothes
- home businesses
- prepared food that is already ready for pickup

Riders does not:

- shop or buy items
- place restaurant orders
- pay merchants for customers
- collect item value, deposits, or cash
- transport people
- assemble or dismantle furniture

## Food Delivery Distinction

Riders is a courier service, not a restaurant ordering platform.

We can deliver food if it is already prepared and ready for pickup. We do not choose, buy, or order food on the customer's behalf.

## Vehicles And Services

- Standard sedan: small sedan, standard/shared route style.
- Express sedan: dedicated/faster delivery.
- Closed box van: for bulky or larger items.
- Refrigerated van: for temperature-sensitive items.
- Helper service: driver plus assistant when available/quoted.

Exact service availability and price are route-specific and must come from `get_price` or active quoted route context.

## Delivery Time Estimates

- Internal areas: standard usually 2-5 hours after order creation; express within around 2 hours.
- External areas: standard usually 3-6 hours after order creation; express within around 3 hours.

These are estimates, not guarantees.

## Working Hours

- Pickup in internal areas: 6:00 AM to 12:00 AM.
- Pickup in external areas: 6:00 AM to 9:00 PM.

## Payment

- Payment is prepaid through cards, in-app wallet, coupons, or tool-confirmed payment links.
- Pay by Receiver, when available through the website, is for the delivery fee only.
- Riders does not collect the value of goods/items from receivers.

## Cancellation And Refund

- Full refund if the order is canceled before the driver arrives at pickup.
- 50% deduction if the driver has reached the pickup area.
- No refund once the item is picked up.
- Returning an item counts as a completed trip back to pickup.

## Tables

All table deliveries require a closed box van. Standard cars cannot be used for tables.

Approximate closed box dimensions:

- Length: 180 cm
- Width: 150 cm
- Height: 120 cm

## Tracking And Driver Number

Tracking through the website shows the driver's number once assigned.

Tracking facts must come from `track_order` or live order state.

## Sender Privacy

Sender details are hidden from the receiver:

- sender name
- sender phone
- sender address

## Multiple Orders And Saved Addresses

Multiple orders and saved addresses are supported through the website after account creation.

Signup/order website: https://order.tryriders.com

## Suspended Areas

No areas are currently listed here as temporarily suspended.

If an area is later listed as suspended, answer from that live/static suspension fact. Do not infer suspension from general knowledge.

## Drivers

- Drivers can be from different nationalities.
- The closest suitable driver is assigned.
- Some cars have Riders branding/logo and some may not yet.

## Company Contracts

Required documents for company delivery contracts:

- articles of association
- latest amendment contract
- commercial license
- authorized signatory from manpower
- recent extract, not older than 5 days
- commercial registry
- manager civil ID
- bank IBAN certificate
- civil ID and power of attorney if an agent signs

Documents should be sent as PDF to: contract@tryriders.com

## Coop Contracts And Apps

For Coop / الجمعيات / التعاونيات requests, use this fixed contact fact:

- Arabic: `يمكنك التواصل مع خدمة عملاء تعاونيات ديليفري عبر واتساب من خلال الرابط المباشر: https://wa.me/9651800242`
- English: `You can contact Coop's Delivery customer service via WhatsApp through this direct link: https://wa.me/9651800242`

This is intentionally fixed contact wording because it points to a separate support channel.

## System Or Payment Error

If the customer reports website/payment failure or sends an error screenshot, use the human-support path. The standard fact to convey is that there is a technical issue and support will help.

Do not claim the issue is fixed unless a tool or human confirms it.

## Official Links

- Website: https://order.tryriders.com
- Android app: https://play.google.com/store/apps/details?id=app.riders.android&pcampaignid=web_share
- Instagram: https://www.instagram.com/try.riders?igsh=MXB2NDY1ZmUza3Zicg==
- Snapchat: https://snapchat.com/t/hoqwyuZh
- TikTok: https://www.tiktok.com/@tryriders

## Area Matching Notes

Area pricing and coverage truth lives in the resolver and pricing sheet, not in this file.

Arabizi hints that may help interpret customer input before sending it to tools:

- `7` often maps to ح, e.g. `7awalli` = Hawalli.
- `9` often maps to ص, e.g. `9bya` = Subiya.
- `5` often maps to خ, e.g. `5aldiya` = Khaldiya.
- `6` often maps to ط, e.g. `6aima` = Taima.
- `3` often maps to ع.
- `2` often maps to ء / أ.
- `8` may map to ق.

Common shorthand examples:

- `frwnya`, `frwaniya` = Farwaniya
- `salmya` = Salmiya
- `7wly` = Hawalli
- `slwa` = Salwa
- `mshrf` = Mishrif
- `mngf` = Mangaf
- `fntas` = Al-Fintas
- `mhboula` = Mahboula
- `fhaheel` = Fahaheel
