"""Report text in English, Hindi and Hinglish.

All user-facing verdict text is templated (never LLM-written), so wording stays calm,
consistent and testable: "high risk based on the evidence", never "100% scam".
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

Lang = str  # "en" | "hi" | "hinglish"

# --------------------------------------------------------------------------- flags: (title, explanation)
FLAGS: dict[str, dict[Lang, tuple[str, str]]] = {
    "brand_lookalike_domain": {
        "en": ("Link imitates {brand}",
               "The link {domain} uses {brand}'s name but isn't {brand}'s website. {brand}'s official site is {official}."),
        "hi": ("लिंक {brand} की नकल करता है",
               "लिंक {domain} में {brand} का नाम है, लेकिन यह {brand} की वेबसाइट नहीं है। {brand} की आधिकारिक वेबसाइट {official} है।"),
        "hinglish": ("Link {brand} ki nakal karta hai",
                     "Link {domain} mein {brand} ka naam hai, par yeh {brand} ki website nahi hai. {brand} ki official website {official} hai."),
    },
    "official_domain_mismatch": {
        "en": ("Link doesn't belong to {org}",
               "{org}'s official website is {official}, but the message points to {domain}."),
        "hi": ("लिंक {org} का नहीं है",
               "{org} की आधिकारिक वेबसाइट {official} है, लेकिन मैसेज {domain} पर ले जाता है।"),
        "hinglish": ("Link {org} ka nahi hai",
                     "{org} ki official website {official} hai, lekin message {domain} par le jaata hai."),
    },
    "authority_unofficial_domain": {
        "en": ("Unofficial link for a {category_label}",
               "A {category_label} uses its own official website (often ending in .gov.in). {domain} is not one of them."),
        "hi": ("{category_label} के नाम पर अनौपचारिक लिंक",
               "{category_label} अपनी आधिकारिक वेबसाइट (अक्सर .gov.in) इस्तेमाल करते हैं। {domain} उनमें से नहीं है।"),
        "hinglish": ("{category_label} ke naam par unofficial link",
                     "{category_label} apni official website (aksar .gov.in) use karte hain. {domain} unmein se nahi hai."),
    },
    "free_email_corporate": {
        "en": ("Sent from a free {provider} address",
               "Offers from {org} wouldn't come from a free email like {email}.{official_part}"),
        "hi": ("मुफ़्त {provider} ईमेल से भेजा गया",
               "{org} के ऑफ़र {email} जैसे मुफ़्त ईमेल से नहीं आते।{official_part}"),
        "hinglish": ("Free {provider} email se bheja gaya",
                     "{org} ke offer {email} jaise free email se nahi aate.{official_part}"),
    },
    "punycode_homograph": {
        "en": ("Link uses look-alike letters",
               "{domain} contains letters from other alphabets that can imitate a familiar website name."),
        "hi": ("लिंक में मिलते-जुलते अक्षर हैं",
               "{domain} में दूसरी लिपियों के अक्षर हैं जो किसी जानी-पहचानी वेबसाइट जैसे दिख सकते हैं।"),
        "hinglish": ("Link mein milte-julte letters hain",
                     "{domain} mein doosri script ke letters hain jo kisi jaani-pehchaani website jaise dikh sakte hain."),
    },
    "phone_reported": {
        "en": ("Number reported online",
               "{phone} appears in {n} scam or complaint report(s) on independent sites ({sites})."),
        "hi": ("इस नंबर की ऑनलाइन शिकायतें हैं",
               "{phone} अलग-अलग वेबसाइटों ({sites}) पर {n} स्कैम/शिकायत रिपोर्ट में मिलता है।"),
        "hinglish": ("Is number ki online complaints hain",
                     "{phone} alag-alag sites ({sites}) par {n} scam/complaint reports mein milta hai."),
    },
    "domain_reported": {
        "en": ("Website reported online",
               "{domain} appears in {n} scam or complaint report(s) ({sites})."),
        "hi": ("इस वेबसाइट की ऑनलाइन शिकायतें हैं",
               "{domain} {n} स्कैम/शिकायत रिपोर्ट ({sites}) में मिलती है।"),
        "hinglish": ("Is website ki online complaints hain",
                     "{domain} {n} scam/complaint reports ({sites}) mein milti hai."),
    },
    "official_contact_mismatch": {
        "en": ("Number not listed by {org}",
               "We searched {official} for {phone} and found no official contact page that lists it."),
        "hi": ("नंबर {org} की सूची में नहीं",
               "हमने {official} पर {phone} खोजा, लेकिन किसी आधिकारिक संपर्क पेज पर यह नंबर नहीं मिला।"),
        "hinglish": ("Number {org} ki list mein nahi",
                     "Humne {official} par {phone} search kiya, par kisi official contact page par yeh number nahi mila."),
    },
    "helpline_is_mobile": {
        "en": ("Helpline is a personal mobile number",
               "{org}'s helplines are listed on {official}, usually as toll-free numbers. {phone} is an ordinary mobile number."),
        "hi": ("हेल्पलाइन एक निजी मोबाइल नंबर है",
               "{org} की हेल्पलाइन {official} पर दी होती है, आमतौर पर टोल-फ़्री नंबर के रूप में। {phone} एक साधारण मोबाइल नंबर है।"),
        "hinglish": ("Helpline ek personal mobile number hai",
                     "{org} ki helplines {official} par di hoti hain, aam taur par toll-free number. {phone} ek normal mobile number hai."),
    },
    "domain_no_footprint": {
        "en": ("Website has no track record",
               "Google has no results for {domain}. Scam sites are often brand new, while genuine organisations are usually easy to find."),
        "hi": ("वेबसाइट का कोई रिकॉर्ड नहीं",
               "Google पर {domain} के लिए कोई नतीजा नहीं मिला। स्कैम वेबसाइटें अक्सर नई होती हैं, जबकि असली संस्थाएँ आसानी से मिल जाती हैं।"),
        "hinglish": ("Website ka koi record nahi",
                     "Google par {domain} ka koi result nahi mila. Scam websites aksar nayi hoti hain, jabki asli organisations aasani se mil jaati hain."),
    },
    "company_no_footprint": {
        "en": ("Company not found online", "We couldn't find an official website or listing for {company}."),
        "hi": ("कंपनी ऑनलाइन नहीं मिली", "{company} की कोई आधिकारिक वेबसाइट या लिस्टिंग नहीं मिली।"),
        "hinglish": ("Company online nahi mili", "{company} ki koi official website ya listing nahi mili."),
    },
    "known_scam_pattern": {
        "en": ("Matches a reported scam",
               "News outlets have reported scams using this kind of message: {n} independent reports ({sites})."),
        "hi": ("यह एक रिपोर्ट किए गए स्कैम जैसा है",
               "समाचार माध्यमों ने ऐसे मैसेज वाले स्कैम की रिपोर्ट की है: {n} अलग-अलग रिपोर्ट ({sites})।"),
        "hinglish": ("Yeh ek reported scam jaisa hai",
                     "News channels ne aise message wale scam report kiye hain: {n} alag reports ({sites})."),
    },
    "org_impersonation_reports": {
        "en": ("{org} is often impersonated", "There are {n} reports of scammers pretending to be {org}."),
        "hi": ("{org} के नाम पर अक्सर धोखा होता है", "{org} बनकर ठगी करने की {n} रिपोर्ट मिलीं।"),
        "hinglish": ("{org} ke naam par aksar dhokha hota hai", "{org} bankar thagi karne ki {n} reports mili."),
    },
    "price_anomaly": {
        "en": ("Price is {pct_below}% below real listings",
               "It's offered at {claimed}, but the same product sells for about {median} (median of {n} listings found by {basis_label})."),
        "hi": ("कीमत असली लिस्टिंग से {pct_below}% कम है",
               "यह {claimed} में बेचा जा रहा है, जबकि यही प्रोडक्ट लगभग {median} में मिलता है ({basis_label} से मिली {n} लिस्टिंग का मध्य मूल्य)।"),
        "hinglish": ("Price asli listings se {pct_below}% kam hai",
                     "Yeh {claimed} mein bik raha hai, jabki yahi product lagbhag {median} ka hai ({basis_label} se mili {n} listings ka median)."),
    },
    "image_reused": {
        "en": ("Product photo appears on other shops",
               "The same photo appears on {n} other sites, including {sites}. Fake sellers often copy photos from real listings."),
        "hi": ("प्रोडक्ट की फ़ोटो दूसरी दुकानों पर भी है",
               "यही फ़ोटो {n} दूसरी वेबसाइटों पर है, जैसे {sites}। नकली विक्रेता अक्सर असली लिस्टिंग की फ़ोटो कॉपी करते हैं।"),
        "hinglish": ("Product ki photo doosri shops par bhi hai",
                     "Yahi photo {n} doosri sites par hai, jaise {sites}. Fake sellers aksar asli listings ki photo copy karte hain."),
    },
    "job_not_listed": {
        "en": ("No matching job listing",
               "Google Jobs shows no listing for {role_part}{company}. Genuine openings are usually posted publicly."),
        "hi": ("ऐसी कोई नौकरी लिस्टेड नहीं",
               "Google Jobs पर {company} में {role_part}कोई लिस्टिंग नहीं मिली। असली नौकरियाँ आमतौर पर सार्वजनिक रूप से पोस्ट होती हैं।"),
        "hinglish": ("Aisi koi job listed nahi",
                     "Google Jobs par {company} mein {role_part}koi listing nahi mili. Asli jobs aam taur par publicly post hoti hain."),
    },
    "address_mismatch": {
        "en": ("Address doesn't match {company_or}",
               "On Google Maps, this address shows {place_desc}, not {company_or}."),
        "hi": ("पता {company_or} से मेल नहीं खाता",
               "Google Maps पर यह पता {place_desc} दिखाता है, {company_or} नहीं।"),
        "hinglish": ("Address {company_or} se match nahi karta",
                     "Google Maps par yeh address {place_desc} dikhata hai, {company_or} nahi."),
    },
    "credential_request": {
        "en": ("Asks for your OTP, PIN or password",
               "Banks and government offices never ask for your OTP, PIN or password."),
        "hi": ("आपका OTP, PIN या पासवर्ड माँगता है",
               "बैंक और सरकारी दफ़्तर कभी भी आपका OTP, PIN या पासवर्ड नहीं माँगते।"),
        "hinglish": ("Aapka OTP, PIN ya password maangta hai",
                     "Bank aur sarkari offices kabhi bhi aapka OTP, PIN ya password nahi maangte."),
    },
    "credential_request:remote_access": {
        "en": ("Asks you to install a screen-sharing app",
               "Screen-sharing apps like AnyDesk let a stranger see and control your phone, including bank apps."),
        "hi": ("स्क्रीन-शेयरिंग ऐप इंस्टॉल करवाता है",
               "AnyDesk जैसे ऐप से कोई अनजान व्यक्ति आपका फ़ोन और बैंक ऐप देख और चला सकता है।"),
        "hinglish": ("Screen-sharing app install karwata hai",
                     "AnyDesk jaise app se koi anjaan aadmi aapka phone aur bank app dekh aur chala sakta hai."),
    },
    "upfront_fee": {
        "en": ("Asks you to pay a fee first",
               "Genuine employers, lenders and prize schemes don't charge a fee before giving you a job, loan or prize."),
        "hi": ("पहले फ़ीस भरने को कहता है",
               "असली कंपनियाँ नौकरी, लोन या इनाम देने से पहले कोई फ़ीस नहीं लेतीं।"),
        "hinglish": ("Pehle fees bharne ko kehta hai",
                     "Asli companies job, loan ya inaam dene se pehle koi fees nahi leti."),
    },
    "threat_or_urgency": {
        "en": ("Uses pressure or threats", "Scammers create panic so you act before you can check."),
        "hi": ("डर या जल्दबाज़ी का दबाव", "ठग डर पैदा करते हैं ताकि आप जाँचने से पहले ही कदम उठा लें।"),
        "hinglish": ("Darr ya jaldbaazi ka pressure", "Thag darr paida karte hain taaki aap check karne se pehle hi action le lo."),
    },
    "payment_request": {
        "en": ("Asks you to pay", "The message asks you to send money through a link, UPI or QR code."),
        "hi": ("पैसे भेजने को कहता है", "मैसेज लिंक, UPI या QR कोड से पैसे भेजने को कहता है।"),
        "hinglish": ("Paise bhejne ko kehta hai", "Message link, UPI ya QR code se paise bhejne ko kehta hai."),
    },
    "ai_injection_text": {
        "en": ("Contains hidden instructions for AI tools",
               "The message includes text trying to tell AI checkers that it's safe. Genuine messages don't do this."),
        "hi": ("AI टूल्स के लिए छिपे निर्देश",
               "मैसेज में AI जाँच टूल्स को 'सुरक्षित' बताने वाला टेक्स्ट है। असली मैसेज ऐसा नहीं करते।"),
        "hinglish": ("AI tools ke liye chupe instructions",
                     "Message mein AI checkers ko 'safe' batane wala text hai. Asli messages aisa nahi karte."),
    },
    "suspicious_tld": {
        "en": ("Unusual website ending ({tld})",
               "Website addresses ending in {tld} are cheap to register and common for short-lived scam sites."),
        "hi": ("असामान्य वेबसाइट एंडिंग ({tld})",
               "{tld} वाले वेब पते सस्ते होते हैं और अक्सर कुछ दिनों के स्कैम साइट्स में इस्तेमाल होते हैं।"),
        "hinglish": ("Unusual website ending ({tld})",
                     "{tld} wale web address saste hote hain aur aksar kuch dino ki scam sites mein use hote hain."),
    },
    "url_shortener": {
        "en": ("Link hides where it goes", "Shortened links hide their real destination."),
        "hi": ("लिंक असली पता छिपाता है", "छोटे (short) लिंक असली वेबसाइट का पता छिपा देते हैं।"),
        "hinglish": ("Link asli address chupata hai", "Short links asli website ka address chupa dete hain."),
    },
    "too_good_to_be_true": {
        "en": ("Promise that's too good to be true", "Easy money for little work is a common hook."),
        "hi": ("ज़रूरत से ज़्यादा अच्छा वादा", "थोड़े काम में आसान कमाई का लालच ठगी का आम तरीका है।"),
        "hinglish": ("Zaroorat se zyada achha promise", "Thode kaam mein aasan kamai ka laalach thagi ka common tareeka hai."),
    },
    "phone_on_official_site": {
        "en": ("Number is listed on {official}", "{phone} appears on the official website {official}."),
        "hi": ("नंबर {official} पर दर्ज है", "{phone} आधिकारिक वेबसाइट {official} पर मिलता है।"),
        "hinglish": ("Number {official} par listed hai", "{phone} official website {official} par milta hai."),
    },
    "domain_official": {
        "en": ("Links go to {org}'s official website", "Every link in the message points to {official}."),
        "hi": ("लिंक {org} की आधिकारिक वेबसाइट के हैं", "मैसेज के सभी लिंक {official} पर जाते हैं।"),
        "hinglish": ("Links {org} ki official website ke hain", "Message ke saare links {official} par jaate hain."),
    },
    "job_listing_match": {
        "en": ("{company} has a matching job listing", "Google Jobs shows a matching opening at {company}."),
        "hi": ("{company} में ऐसी नौकरी लिस्टेड है", "Google Jobs पर {company} में मिलती-जुलती नौकरी दिखती है।"),
        "hinglish": ("{company} mein aisi job listed hai", "Google Jobs par {company} mein milti-julti job dikhti hai."),
    },
    "maps_business_match": {
        "en": ("Address matches {company} on Maps", "Google Maps shows {company} at this address."),
        "hi": ("पता Maps पर {company} से मेल खाता है", "Google Maps पर इस पते पर {company} दिखता है।"),
        "hinglish": ("Address Maps par {company} se match karta hai", "Google Maps par is address par {company} dikhta hai."),
    },
    "price_plausible": {
        "en": ("Price is in the normal range", "{claimed} is close to the typical price of {median}."),
        "hi": ("कीमत सामान्य है", "{claimed} आम कीमत {median} के आसपास है।"),
        "hinglish": ("Price normal hai", "{claimed} aam price {median} ke aas-paas hai."),
    },
}

CATEGORY_LABEL = {
    "en": {"government": "government office", "utility": "electricity or utility company", "bank": "bank",
           "telecom": "telecom company"},
    "hi": {"government": "सरकारी विभाग", "utility": "बिजली/यूटिलिटी कंपनी", "bank": "बैंक", "telecom": "टेलीकॉम कंपनी"},
    "hinglish": {"government": "sarkari vibhaag", "utility": "bijli/utility company", "bank": "bank",
                 "telecom": "telecom company"},
}

LEVELS: dict[Lang, dict[str, tuple[str, str]]] = {
    "en": {
        "HIGH_RISK": ("High risk", "Strong warning signs, backed by sources."),
        "SUSPICIOUS": ("Be careful", "We found inconsistencies, but not enough to be sure."),
        "LOW_RISK": ("No major warning signs", "This doesn't guarantee it's genuine."),
        "UNVERIFIED": ("Couldn't verify", "We didn't find enough reliable evidence either way."),
    },
    "hi": {
        "HIGH_RISK": ("ज़्यादा जोखिम", "स्रोतों से पुष्ट गंभीर चेतावनी संकेत।"),
        "SUSPICIOUS": ("सावधान रहें", "कुछ गड़बड़ियाँ मिलीं, लेकिन पक्का कहने के लिए काफ़ी नहीं।"),
        "LOW_RISK": ("कोई बड़ा चेतावनी संकेत नहीं", "इसका मतलब यह नहीं कि यह पक्का असली है।"),
        "UNVERIFIED": ("पुष्टि नहीं हो सकी", "किसी भी तरफ़ पर्याप्त भरोसेमंद सबूत नहीं मिले।"),
    },
    "hinglish": {
        "HIGH_RISK": ("High risk", "Sources se confirm hue serious warning signs."),
        "SUSPICIOUS": ("Saavdhaan rahein", "Kuch gadbad mili, par pakka kehne ke liye kaafi nahi."),
        "LOW_RISK": ("Koi bada warning sign nahi", "Iska matlab yeh nahi ki yeh pakka asli hai."),
        "UNVERIFIED": ("Verify nahi ho saka", "Kisi bhi taraf kaafi bharosemand saboot nahi mile."),
    },
}

HEADLINES: dict[Lang, dict[str, str]] = {
    "en": {
        "HIGH_RISK:impersonation": "{n} independent warning signs suggest this message is impersonating {target}.",
        "HIGH_RISK:fake_customer_care": "This customer-care contact shows {n} independent warning signs.",
        "HIGH_RISK:shopping_deal": "This deal shows {n} warning signs of a fake seller.",
        "HIGH_RISK:job_offer": "This job offer shows {n} warning signs of a recruitment scam.",
        "HIGH_RISK": "This message shows {n} independent warning signs.",
        "SUSPICIOUS": "We found {n} warning sign(s), but not enough to be sure. Verify through an official channel before acting.",
        "SUSPICIOUS:mixed": "Mixed evidence: some details check out with {target}, others look like a scam.",
        "LOW_RISK": "We found no major warning signs in what we could check.",
        "LOW_RISK:trust": "We found no major warning signs, and {official} confirms the details we checked.",
        "UNVERIFIED": "We couldn't find enough evidence to say whether this is genuine.",
    },
    "hi": {
        "HIGH_RISK:impersonation": "{n} अलग-अलग चेतावनी संकेत बताते हैं कि यह मैसेज {target} के नाम पर धोखा है।",
        "HIGH_RISK:fake_customer_care": "इस कस्टमर-केयर संपर्क में {n} अलग-अलग चेतावनी संकेत मिले।",
        "HIGH_RISK:shopping_deal": "इस डील में नकली विक्रेता के {n} चेतावनी संकेत मिले।",
        "HIGH_RISK:job_offer": "इस नौकरी के ऑफ़र में भर्ती-धोखाधड़ी के {n} चेतावनी संकेत मिले।",
        "HIGH_RISK": "इस मैसेज में {n} अलग-अलग चेतावनी संकेत मिले।",
        "SUSPICIOUS": "{n} चेतावनी संकेत मिले, लेकिन पक्का कहने के लिए काफ़ी नहीं। कुछ भी करने से पहले आधिकारिक माध्यम से जाँच लें।",
        "SUSPICIOUS:mixed": "मिले-जुले सबूत: कुछ बातें {target} से मेल खाती हैं, कुछ धोखे जैसी लगती हैं।",
        "LOW_RISK": "जो हम जाँच पाए, उसमें कोई बड़ा चेतावनी संकेत नहीं मिला।",
        "LOW_RISK:trust": "कोई बड़ा चेतावनी संकेत नहीं मिला, और {official} हमारी जाँची गई जानकारी की पुष्टि करता है।",
        "UNVERIFIED": "यह असली है या नहीं, यह कहने के लिए पर्याप्त सबूत नहीं मिले।",
    },
    "hinglish": {
        "HIGH_RISK:impersonation": "{n} alag warning signs batate hain ki yeh message {target} ke naam par dhokha hai.",
        "HIGH_RISK:fake_customer_care": "Is customer-care contact mein {n} alag warning signs mile.",
        "HIGH_RISK:shopping_deal": "Is deal mein fake seller ke {n} warning signs mile.",
        "HIGH_RISK:job_offer": "Is job offer mein recruitment scam ke {n} warning signs mile.",
        "HIGH_RISK": "Is message mein {n} alag warning signs mile.",
        "SUSPICIOUS": "{n} warning sign mile, par pakka kehne ke liye kaafi nahi. Kuch bhi karne se pehle official channel se check karein.",
        "SUSPICIOUS:mixed": "Mixed saboot: kuch baatein {target} se match karti hain, kuch scam jaisi lagti hain.",
        "LOW_RISK": "Jo hum check kar paaye, usmein koi bada warning sign nahi mila.",
        "LOW_RISK:trust": "Koi bada warning sign nahi mila, aur {official} check ki gayi details confirm karta hai.",
        "UNVERIFIED": "Yeh asli hai ya nahi, yeh kehne ke liye kaafi saboot nahi mile.",
    },
}

TARGET_GENERIC = {
    "en": {"utility": "an electricity company", "bank": "a bank", "government": "a government office",
           "courier": "a courier company", "telecom": "a telecom company", None: "a real organisation"},
    "hi": {"utility": "बिजली कंपनी", "bank": "बैंक", "government": "सरकारी विभाग", "courier": "कूरियर कंपनी",
           "telecom": "टेलीकॉम कंपनी", None: "किसी असली संस्था"},
    "hinglish": {"utility": "bijli company", "bank": "bank", "government": "sarkari vibhaag",
                 "courier": "courier company", "telecom": "telecom company", None: "kisi asli organisation"},
}

RECS: dict[str, dict[Lang, str]] = {
    "dont_click": {"en": "Don't click the link or open any attachment.",
                   "hi": "लिंक पर क्लिक न करें और कोई अटैचमेंट न खोलें।",
                   "hinglish": "Link par click na karein aur koi attachment na kholein."},
    "dont_call": {"en": "Don't call or reply to the number in the message.",
                  "hi": "मैसेज में दिए नंबर पर कॉल या जवाब न करें।",
                  "hinglish": "Message mein diye number par call ya reply na karein."},
    "dont_pay": {"en": "Don't send money or share your OTP, PIN or passwords.",
                 "hi": "पैसे न भेजें और अपना OTP, PIN या पासवर्ड किसी को न बताएँ।",
                 "hinglish": "Paise na bhejein aur apna OTP, PIN ya password kisi ko na batayein."},
    "official_channel": {"en": "Contact {org} only through its official website: {official}.",
                         "hi": "{org} से सिर्फ़ उसकी आधिकारिक वेबसाइट से संपर्क करें: {official}।",
                         "hinglish": "{org} se sirf uski official website se contact karein: {official}."},
    "official_channel_generic": {"en": "Contact the organisation only through its official website or app.",
                                 "hi": "संस्था से सिर्फ़ उसकी आधिकारिक वेबसाइट या ऐप से संपर्क करें।",
                                 "hinglish": "Organisation se sirf uski official website ya app se contact karein."},
    "report": {"en": "Report it: call 1930 or visit cybercrime.gov.in. Report fraud calls and SMS on Sanchar Saathi (Chakshu).",
               "hi": "शिकायत करें: 1930 पर कॉल करें या cybercrime.gov.in पर जाएँ। फ़र्ज़ी कॉल/SMS की शिकायत संचार साथी (चक्षु) पर करें।",
               "hinglish": "Report karein: 1930 par call karein ya cybercrime.gov.in par jaayein. Fraud calls/SMS ki complaint Sanchar Saathi (Chakshu) par karein."},
    "already_paid": {"en": "Already paid or shared details? Call 1930 immediately and inform your bank.",
                     "hi": "पैसे भेज दिए या जानकारी दे दी? तुरंत 1930 पर कॉल करें और अपने बैंक को बताएँ।",
                     "hinglish": "Paise bhej diye ya details de di? Turant 1930 par call karein aur apne bank ko batayein."},
    "otp_never": {"en": "No bank or government office will ever ask for your OTP, PIN or password.",
                  "hi": "कोई भी बैंक या सरकारी दफ़्तर कभी आपका OTP, PIN या पासवर्ड नहीं माँगता।",
                  "hinglish": "Koi bhi bank ya sarkari office kabhi aapka OTP, PIN ya password nahi maangta."},
    "no_fee_jobs": {"en": "Genuine employers never charge a fee for a job.",
                    "hi": "असली कंपनियाँ नौकरी के लिए कभी फ़ीस नहीं लेतीं।",
                    "hinglish": "Asli companies job ke liye kabhi fees nahi leti."},
    "buy_official": {"en": "Buy from the brand's official store or a well-known marketplace.",
                     "hi": "ब्रांड के आधिकारिक स्टोर या जानी-मानी वेबसाइट से ही खरीदें।",
                     "hinglish": "Brand ke official store ya jaani-maani website se hi kharidein."},
    "digital_arrest": {"en": "Police and CBI never conduct 'digital arrests' over video calls.",
                       "hi": "पुलिस और CBI कभी वीडियो कॉल पर 'डिजिटल अरेस्ट' नहीं करते।",
                       "hinglish": "Police aur CBI kabhi video call par 'digital arrest' nahi karte."},
    "verify_first": {"en": "Don't act on this message directly. Verify it through the official website or helpline first.",
                     "hi": "इस मैसेज पर सीधे कुछ न करें। पहले आधिकारिक वेबसाइट या हेल्पलाइन से पुष्टि करें।",
                     "hinglish": "Is message par seedhe kuch na karein. Pehle official website ya helpline se confirm karein."},
    "stay_alert": {"en": "Still, never share your OTP, PIN or password, even with genuine senders.",
                   "hi": "फिर भी, अपना OTP, PIN या पासवर्ड किसी को न बताएँ, असली भेजने वाले को भी नहीं।",
                   "hinglish": "Phir bhi, apna OTP, PIN ya password kisi ko na batayein, asli sender ko bhi nahi."},
    "unverified": {"en": "Treat any request for money or OTP with caution.",
                   "hi": "पैसे या OTP की किसी भी माँग पर सावधानी बरतें।",
                   "hinglish": "Paise ya OTP ki kisi bhi maang par saavdhaani rakhein."},
}

UI: dict[Lang, dict[str, str]] = {
    "en": {"confidence": "{done} of {planned} checks completed · {n} independent source(s)",
           "confidence_none": "No web checks were possible for this input",
           "confidence_nothing": "There's no phone number, link, organisation or product here that can be checked",
           "lens": "Google Lens", "shopping": "Google Shopping", "role_part": "{role} at ",
           "official_part": " {org}'s official domain is {official}.", "places_res": "residential buildings or hotels",
           "places_other": "other places", "places_none": "no matching place", "company_generic": "the company's office"},
    "hi": {"confidence": "{planned} में से {done} जाँच पूरी · {n} स्वतंत्र स्रोत",
           "confidence_none": "इस इनपुट के लिए वेब जाँच संभव नहीं थी",
           "confidence_nothing": "इसमें कोई फ़ोन नंबर, लिंक, संस्था या प्रोडक्ट नहीं है जिसे जाँचा जा सके",
           "lens": "Google Lens", "shopping": "Google Shopping", "role_part": "{role} की ",
           "official_part": " {org} का आधिकारिक डोमेन {official} है।", "places_res": "रिहायशी इमारतें या होटल",
           "places_other": "दूसरी जगहें", "places_none": "कोई मिलती-जुलती जगह नहीं", "company_generic": "कंपनी का दफ़्तर"},
    "hinglish": {"confidence": "{planned} mein se {done} checks poore · {n} independent sources",
                 "confidence_none": "Is input ke liye web check possible nahi tha",
                 "confidence_nothing": "Ismein koi phone number, link, organisation ya product nahi hai jise check kiya ja sake",
                 "lens": "Google Lens", "shopping": "Google Shopping", "role_part": "{role} ki ",
                 "official_part": " {org} ka official domain {official} hai.", "places_res": "residential buildings ya hotels",
                 "places_other": "doosri jagah", "places_none": "koi milti-julti jagah nahi", "company_generic": "company ka office"},
}


def fmt(template: str, facts: dict[str, Any]) -> str:
    return template.format_map(defaultdict(str, {k: ("" if v is None else v) for k, v in facts.items()}))


def flag_text(signal_id: str, detail: str | None, lang: Lang, facts: dict[str, Any]) -> tuple[str, str]:
    key = f"{signal_id}:{detail}" if detail and f"{signal_id}:{detail}" in FLAGS else signal_id
    title, expl = FLAGS[key].get(lang) or FLAGS[key]["en"]
    ui = UI[lang]
    facts = dict(facts)
    facts.setdefault("category_label", CATEGORY_LABEL[lang].get(facts.get("category"), facts.get("category") or ""))
    facts["basis_label"] = ui["lens"] if facts.get("basis") == "lens" else ui["shopping"]
    facts["role_part"] = fmt(ui["role_part"], facts) if facts.get("role") else ""
    facts["official_part"] = fmt(ui["official_part"], facts) if facts.get("official") else ""
    if signal_id == "address_mismatch":
        facts["company_or"] = facts.get("company") or ui["company_generic"]
        facts["place_desc"] = (ui["places_res"] if facts.get("n_residential") else
                               ui["places_other"] if facts.get("n_places") else ui["places_none"])
    if signal_id == "free_email_corporate" and not facts.get("org"):
        facts["org"] = {"en": "a company", "hi": "कंपनी", "hinglish": "company"}[lang]
    return fmt(title, facts), fmt(expl, facts)


def report_language(graph_language: str, override: str, haystack: str) -> Lang:
    if override in ("en", "hi", "hinglish"):
        return override
    if graph_language == "hi":
        return "hi"
    if graph_language == "mixed":
        return "hi" if any("ऀ" <= ch <= "ॿ" for ch in haystack) else "hinglish"
    if graph_language == "hinglish":
        return "hinglish"
    return "en"
