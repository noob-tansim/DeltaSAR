/**
 * Every sentence the phone app shows or speaks: [Bangla, English].
 * The Bangla lines are drafts. Lines marked NEW are not in event_kit/05_bangla_copy_sheet.md yet
 * and need the same check by a native reader.
 */
export type Lang = 'bn' | 'en';

const S = {
  appName: ['বন্যা সাথী', 'Bonna Sathi'],
  listen: ['শুনুন', 'Listen'],
  help: ['সাহায্য', 'Help'],
  back: ['ফিরে যান', 'Back'], // NEW
  loading: ['অপেক্ষা করুন…', 'Please wait…'], // NEW
  save: ['সংরক্ষণ করুন', 'Save'], // NEW
  saved: ['সংরক্ষণ হয়েছে', 'Saved'], // NEW
  noVoice: ['এই ডিভাইসে বাংলা কণ্ঠ নেই।', 'This device has no Bangla voice.'], // NEW
  readInEnglish: ['ইংরেজিতে শুনুন', 'Listen in English'], // NEW
  stop: ['থামান', 'Stop'], // NEW
  chooseByListening: ['শুনে বেছে নিন', 'Choose by listening'],
  modePictures: ['ছবি দেখে', 'By pictures'],
  modePicturesSub: ['কম লেখা, বড় ছবি', 'Less text, big pictures'],
  sylheti: ['সিলেটি (শীঘ্রই)', 'Sylheti (soon)'],
  laterChange: ['পরে সেটিংসে বদলাতে পারবেন', 'You can change this later in settings'],
  change: ['বদলান', 'Change'],
  demoTag: ['ডেমো', 'demo'],
  chCallPlain: ['ফোন কল', 'Phone call'],
  chSmsPlain: ['এসএমএস', 'SMS'],
  radarSeen: ['রাডারে নতুন পানি দেখা গেছে', 'Radar has seen new water'],
  rainTile: ['বৃষ্টি', 'Rain'],
  minutes: ['মিনিট', 'min'],
  sourceLine: ['সূত্র: NASA-ISRO NISAR, NASA IMERG, FFWC।', 'Sources: NASA-ISRO NISAR, NASA IMERG, FFWC.'], // NEW
  evidenceReceipt: ['প্রমাণ (evidence receipt)', 'Evidence receipt'],
  showAll: ['সব দেখুন', 'Show all'], // NEW
  rainOver: ['আপনার সীমার বেশি', 'Above your level'],
  rainUnder: ['আপনার সীমার নিচে', 'Below your level'], // NEW
  changeLevel: ['আমার সীমা বদলান', 'Change my level'],
  close: ['বন্ধ করুন', 'Close'], // NEW
  next: ['পরের ধাপ', 'Next'],
  navHome: ['হোম', 'Home'], // NEW
  navAlerts: ['সতর্কবার্তা', 'Alerts'],
  navSettings: ['সেটিংস', 'Settings'], // NEW
  replayShort: ['রিপ্লে', 'REPLAY'], // NEW
  replayLong: ['আগের তারিখের আসল তথ্য', 'real data from a past date'], // NEW
  tagline: ['রাডারে দেখা নদীর পানি ও ভাঙনের খবর। স্বেচ্ছাসেবক যাচাই করেন, ফোন পড়ে শোনায়।', 'River water and bank changes seen by NISAR radar. Checked by a volunteer, read aloud by your phone.'], // NEW
  helpAbout: ['রাডারের তথ্য নাসা ও ইসরোর NISAR উপগ্রহ থেকে। প্রতিটি সতর্কবার্তা একজন স্বেচ্ছাসেবক যাচাই করেন।', 'Radar data comes from the NASA-ISRO NISAR satellite. A volunteer checks every alert.'], // NEW
  areaWhy: ['আপনার বাড়ির কাছের পানির খবর দিতে এলাকা জানা দরকার।', 'We need your area to tell you about water near your home.'], // NEW
  suggested: ['নদীর পাড়ের ইউনিয়ন', 'Riverside unions'], // NEW
  whatYouGet: ['কী কী জানাবো?', 'What should we tell you about?'], // NEW
  ruleRadar: ['বাড়ির কাছে নতুন পানি', 'New water near home'], // NEW
  ruleRadarSub: ['রাডার ছবিতে দেখা গেলে', 'When the radar picture shows it'], // NEW
  ruleRiver: ['নদী বিপদসীমার কাছে', 'River near danger level'], // NEW
  ruleRiverSub: ['FFWC-এর মাপ অনুযায়ী', 'From FFWC readings'], // NEW
  ruleRain: ['ভারী বৃষ্টি', 'Heavy rain'],
  ruleRainSub: ['২৪ ঘণ্টায় ৩ ইঞ্চি বা বেশি', '3 inches or more in 24 hours'], // NEW
  moreOptions: ['আরও সুবিধা', 'More options'], // NEW
  changeArea: ['এলাকা বদলান', 'Change my area'], // NEW
  alertAnswered: ['সতর্কবার্তা · উত্তর দেওয়া হয়েছে', 'Alert · answered'], // NEW
  metre: ['মিটার', 'm'],
  mmUnit: ['মিমি', 'mm'],
  dangerLevel: ['বিপদসীমা', 'danger level'],
  yourLevel: ['আপনার সীমা', 'your level'], // NEW
  rainNone: ['বৃষ্টির তথ্য নেই', 'No rain value'], // NEW
  notOfficial: ['এটি সরকারি সতর্কবার্তা নয়।', 'This is not an official warning.'],
  call1090: ['সরকারি পূর্বাভাস শুনতে ১০৯০ নম্বরে বিনা খরচে ফোন করুন', 'Call 1090 free to hear the official forecast'],
  call1090Button: ['১০৯০ নম্বরে ফোন করুন', 'Call 1090'], // NEW
  replay: ['রিপ্লে · আগের তারিখের আসল তথ্য', 'REPLAY · real data from a past date'], // NEW
  offline: ['ইন্টারনেট নেই। শেষ পাওয়া তথ্য দেখাচ্ছে', 'No internet. Showing the last information received'],

  // join
  joinTitle: ['কীভাবে খবর পেতে চান?', 'How do you want to get news?'],
  howUse: ['কীভাবে ব্যবহার করবেন?', 'How will you use it?'],
  modeListen: ['শুনে শুনে', 'By listening'],
  modeListenSub: ['সব লেখা পড়ে শোনাবে', 'Reads all text aloud'],
  modeLarge: ['বড় লেখা', 'Large text'],
  modeLargeSub: ['সব লেখা বড় হবে', 'All text gets bigger'],
  modeVibrate: ['কাঁপুনি ও আলো', 'Vibration and light'],
  modeVibrateSub: ['শব্দ ছাড়াই সতর্কতা', 'Alerts without sound'],
  myArea: ['আমার এলাকা', 'My area'],
  chooseUnion: ['আপনার ইউনিয়ন বেছে নিন', 'Choose your union'], // NEW
  searchUnion: ['ইউনিয়ন বা উপজেলার নাম লিখুন', 'Type a union or upazila name'], // NEW
  coverage: ['যমুনা নদীর পাড়ের {n}টি ইউনিয়ন · সিরাজগঞ্জ, টাঙ্গাইল, বগুড়া, জামালপুর ও পাবনা জেলা', '{n} unions along the Jamuna river · Sirajganj, Tangail, Bogura, Jamalpur and Pabna districts'], // NEW
  notCovered: ['“{q}” আমাদের এলাকায় নেই। বন্যা সাথী এখন শুধু যমুনা নদীর পাড়ের এই ইউনিয়নগুলোতে কাজ করে, কারণ রাডারের হিসাব এই এলাকার জন্যই করা। নিচ থেকে আপনার সবচেয়ে কাছের ইউনিয়ন বেছে নিন।', '“{q}” is not in our area. বন্যা সাথী works only in these unions along the Jamuna for now, because the radar analysis covers this reach. Choose the union nearest to you below.'], // NEW
  findNearest: ['আমার কাছের ইউনিয়ন খুঁজুন', 'Find my nearest union'], // NEW
  nearestOutside: ['আপনি এখন আমাদের এলাকার বাইরে আছেন। তালিকা থেকে ইউনিয়ন বেছে নিন।', 'You are outside our area right now. Choose a union from the list.'], // NEW
  unionsLoading: ['ইউনিয়নের তালিকা আসছে…', 'Loading the union list…'], // NEW
  unionsWaking: ['সার্ভার চালু হচ্ছে, তালিকা একটু পরে আসবে…', 'The server is waking up; the list will appear in a moment…'], // NEW
  unionsFailed: ['তালিকা আনা যায়নি।', 'Could not load the list.'], // NEW
  tryAgain: ['আবার চেষ্টা করুন', 'Try again'], // NEW
  homePlace: ['বাড়ির জায়গা', 'Home location'], // NEW
  homeAtCentre: ['ইউনিয়নের মাঝখান ধরা হয়েছে', 'The centre of the union is used'], // NEW
  useMyLocation: ['আমার এখনকার জায়গা নিন', 'Use where I am now'], // NEW
  locationOutside: ['এই জায়গাটি আমাদের এলাকার বাইরে। ইউনিয়নের মাঝখান রাখা হলো।', 'This place is outside the covered area. The union centre is kept.'], // NEW
  locationFailed: ['জায়গা পাওয়া যায়নি', 'Location not available'], // NEW
  chApp: ['অ্যাপে সতর্কতা', 'App alert'],
  chAppSub: ['কাঁপুনি ও আলো সহ', 'With vibration and light'],
  chEmail: ['ইমেইল', 'Email'],
  chEmailSub: ['অফিস ও স্বেচ্ছাসেবকদের জন্য', 'For offices and volunteers'],
  chCall: ['ফোন কল (ডেমো)', 'Phone call (demo)'],
  chCallSub: ['যেকোনো ফোনে, পড়তে হবে না', 'On any phone, no reading needed'],
  chSms: ['এসএমএস (ডেমো)', 'SMS (demo)'],
  chSmsSub: ['লেখা পড়তে পারলে', 'If you can read'],
  emailField: ['ইমেইল ঠিকানা', 'Email address'], // NEW
  nameField: ['নাম (না দিলেও চলবে)', 'Name (optional)'], // NEW
  privacy: ['আপনার নম্বর শুধু সতর্কবার্তার জন্য। যেকোনো সময় বাদ দিতে পারবেন।', 'Your details are only for alerts. You can remove them any time.'],
  consent: ['আমি রাজি', 'I agree'], // NEW
  start: ['শুরু করুন', 'Start'],
  needUnion: ['আগে ইউনিয়ন বেছে নিন', 'Choose a union first'], // NEW
  needConsent: ['"আমি রাজি" ঘরে টিক দিন', 'Tick "I agree"'], // NEW
  needEmail: ['ইমেইল ঠিকানা লিখুন', 'Enter an email address'], // NEW
  demoNote: ['এটি একটি ডেমো। শুধু দলের সদস্য ও রাজি হওয়া পরীক্ষকদের তথ্য রাখা হয়।', 'This is a demo. Only team members and consenting testers are stored.'], // NEW

  // home
  calm: ['এখন কোনো সতর্কবার্তা নেই', 'No alert now'], // NEW
  watch: ['সতর্ক থাকুন', 'Stay alert'],
  alert: ['সতর্কবার্তা', 'Alert'],
  no_data: ['নতুন তথ্য নেই', 'No new information'],
  radarNoNewWater: ['শেষ রাডার ছবিতে আপনার কাছে নতুন পানি দেখা যায়নি', 'The last radar picture shows no new water near you'], // NEW
  radarNone: ['এখনও কোনো রাডার ছবি নেই', 'No radar picture yet'], // NEW
  verified: ['যাচাই করা', 'Verified'],
  provisional: ['প্রাথমিক তথ্য', 'Provisional data'],
  oldInfo: ['পুরোনো তথ্য', 'Old information'], // NEW
  gap: ['রাডার ১০ আগস্ট পর্যন্ত বন্ধ। নদীর খবর নিচে।', 'Radar is off until 10 August. River news below.'],
  riverTitle: ['নদীর পানি', 'River level'], // NEW
  riverNone: ['নদীর নতুন খবর নেই', 'No river reading'], // NEW
  rainTitle: ['বৃষ্টি, ২৪ ঘণ্টা', 'Rain, 24 hours'], // NEW
  map: ['মানচিত্র', 'Map'],
  myAlerts: ['আমার সতর্কতা', 'My alerts'],
  pastAlerts: ['আগের সতর্কবার্তা', 'Past alerts'], // NEW
  noPastAlerts: ['এখনও কোনো সতর্কবার্তা আসেনি', 'No alerts yet'], // NEW
  openAlert: ['সতর্কবার্তা খুলুন', 'Open the alert'], // NEW
  sources: ['তথ্যের উৎস', 'Data sources'], // NEW

  // alert
  safe: ['আমি নিরাপদ', 'I am safe'],
  needHelp: ['সাহায্য দরকার', 'I need help'],
  holdHint: ['ভুল চাপ এড়াতে চেপে ধরে রাখুন', 'Press and hold to avoid a wrong tap'],
  whatToDo: ['এখনই যা করবেন', 'What to do now'],
  todo1: ['গবাদিপশু উঁচু জায়গায় নিন', 'Move cattle to high ground'],
  todo2: ['শুকনো খাবার ও পানি রাখুন', 'Keep dry food and water'],
  todo3: ['ফোন চার্জ দিয়ে রাখুন', 'Keep the phone charged'],
  sure: ['নিশ্চিত', 'Sure'], // NEW
  less_sure: ['পুরোপুরি নিশ্চিত নয়', 'Less sure'], // NEW
  unknown: ['জানা নেই', 'Unknown'],
  howSure: ['কতটা নিশ্চিত', 'How sure'],
  verifiedBy: ['যাচাই করেছেন', 'Verified by'],
  replySafeGot: ['আপনার খবর পেয়েছি: আপনি নিরাপদ। ধন্যবাদ। নিরাপদে থাকুন।', 'We have your message: you are safe. Thank you. Stay safe.'],
  replyHelpGot: ['আপনার খবর পেয়েছি। একজন স্বেচ্ছাসেবক আপনাকে ফোন করবেন।', 'We have your message. A volunteer will call you.'],
  replyQueued: ['নেটওয়ার্ক এলে পাঠানো হবে', 'Will be sent when there is network'], // NEW
  changeReply: ['উত্তর বদলান', 'Change my answer'], // NEW
  seeEvidence: ['কী দেখা গেছে, দেখুন', 'See what was seen'], // NEW
  pressKeys: ['নিরাপদ থাকলে ১ চাপুন। সাহায্য লাগলে ২ চাপুন।', 'Press 1 if you are safe, 2 if you need help.'],
  alertMissing: ['এই সতর্কবার্তাটি পাওয়া যায়নি', 'This alert was not found'], // NEW

  // evidence
  evidence: ['কী দেখা গেছে', 'What was seen'],
  receipt: ['রসিদ', 'Receipt'], // NEW
  receiptHint: ['প্রতিটি সংখ্যা কোথা থেকে এসেছে', 'Where each number comes from'], // NEW
  radarBefore: ['আগে', 'Before'],
  radarAfter: ['পরে', 'After'],

  // settings
  whichMonths: ['কোন মাসে জানাবো?', 'In which months should we tell you?'],
  howMuchRain: ['কতটা বৃষ্টি হলে জানাবো? (২৪ ঘণ্টায়)', 'How much rain before we tell you? (in 24 hours)'],
  rain3: ['৩ ইঞ্চি, ভারী বৃষ্টি', '3 inches, heavy'],
  rain6: ['৬ ইঞ্চি, অতি ভারী', '6 inches, very heavy'],
  rainCustom: ['নিজে ঠিক করুন', 'Set your own'],
  riverSwitch: ['নদী বিপদসীমা ছুঁলে', 'When the river reaches danger level'],
  radarSwitch: ['রাডারে কাছে নতুন পানি দেখলে', 'When radar sees new water nearby'],
  radarDistance: ['বাড়ি থেকে কত দূর পর্যন্ত', 'How far from home'], // NEW
  emailSwitch: ['ইমেইলেও জানাবো?', 'Tell you by email too?'],
  removeMe: ['আমার তথ্য মুছে ফেলুন', 'Remove my details'], // NEW
  removeConfirm: ['আপনার যোগাযোগের তথ্য মুছে যাবে এবং সব সতর্কতা বন্ধ হবে। ঠিক আছে?', 'Your contact details will be removed and all alerts switched off. OK?'], // NEW
  language: ['English', 'বাংলা'],

  // map
  legendRiver: ['নদী', 'River'],
  legendNewWater: ['নতুন পানি', 'New water'],
  legendUnknown: ['জানা নেই', 'Unknown'],
  legendHome: ['আমার বাড়ি', 'My home'], // NEW
  viewSimple: ['সহজ', 'Simple'],
  viewRadar: ['রাডার', 'Radar'],
  radarLayerFailed: ['রাডার ছবি এখন আনা যাচ্ছে না', 'The radar picture cannot be loaded now'], // NEW
  mapUnavailable: ['এই ফোনে মানচিত্র দেখানো যাচ্ছে না', 'The map cannot be shown on this phone'], // NEW
  gapNote: ['২৭ জুলাই থেকে ১০ আগস্ট রাডার বন্ধ ছিল', 'Radar was off from 27 July to 10 August'],
} as const satisfies Record<string, readonly [string, string]>;

export type StrKey = keyof typeof S;

export function tr(key: StrKey, lang: Lang): string {
  return S[key][lang === 'bn' ? 0 : 1];
}

const BN_MONTHS = ['জানু', 'ফেব্রু', 'মার্চ', 'এপ্রিল', 'মে', 'জুন', 'জুলাই', 'আগস্ট', 'সেপ্টে', 'অক্টো', 'নভে', 'ডিসে'];
const EN_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function monthName(m: number, lang: Lang): string {
  return (lang === 'bn' ? BN_MONTHS : EN_MONTHS)[m - 1] ?? String(m);
}

const bnFmt = new Intl.NumberFormat('bn-BD', { useGrouping: false, maximumFractionDigits: 2 });
/** A number in the digits of the chosen language. */
export function num(v: number, lang: Lang): string {
  return lang === 'bn' ? bnFmt.format(v) : String(Math.round(v * 100) / 100);
}

/** Date and time in Asia/Dhaka, in the chosen language: "২৭ জুলাই, ১৩:২২" / "27 July, 13:22". */
export function when(iso: string, lang: Lang, withTime = true): string {
  const loc = lang === 'bn' ? 'bn-BD' : 'en-GB';
  const d = new Date(iso);
  const date = new Intl.DateTimeFormat(loc, { timeZone: 'Asia/Dhaka', day: 'numeric', month: 'long' }).format(d);
  if (!withTime) return date;
  const time = new Intl.DateTimeFormat(loc, { timeZone: 'Asia/Dhaka', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(d);
  return `${date}, ${time}`;
}

// ---- sentences with numbers (all NEW except where the copy sheet has the same pattern)
export const say = {
  newWaterWalk: (minutes: number, lang: Lang) =>
    lang === 'bn'
      ? `রাডারে আপনার বাড়ি থেকে ${num(minutes, lang)} মিনিট হাঁটা দূরে নতুন পানি দেখা গেছে`
      : `Radar saw new water about ${minutes} minutes' walk from your home`,
  pictureAge: (dateIso: string, days: number, lang: Lang) =>
    lang === 'bn'
      ? `রাডার ছবি: ${when(dateIso, lang, false)}, ${num(Math.floor(days), lang)} দিন আগে`
      : `Radar picture: ${when(dateIso, lang, false)}, ${Math.floor(days)} days ago`,
  nextPass: (dateIso: string, lang: Lang) =>
    lang === 'bn' ? `পরের রাডার ছবি আশা করা যায়: ${when(dateIso, lang, false)}` : `Next radar picture expected: ${when(dateIso, lang, false)}`,
  river: (station: string, level: number, danger: number, lang: Lang) =>
    lang === 'bn'
      ? `যমুনা, ${station} পয়েন্ট: পানি ${num(level, lang)} মিটার। বিপদসীমা ${num(danger, lang)} মিটার।`
      : `Jamuna at ${station}: water level ${level} m. Danger level ${danger} m.`,
  rain: (mm: number, limit: number, lang: Lang) =>
    lang === 'bn' ? `${num(mm, lang)} মিমি। আপনার সীমা ${num(limit, lang)} মিমি।` : `${mm} mm. Your level is ${limit} mm.`,
  walkOnly: (minutes: number, lang: Lang) => (lang === 'bn' ? `আপনার বাড়ি থেকে ${num(minutes, lang)} মিনিট হাঁটা দূরে` : `About ${minutes} minutes' walk from your home`),
  step: (n: number, of: number, lang: Lang) => (lang === 'bn' ? `ধাপ ${num(n, lang)} / ${num(of, lang)}` : `Step ${n} / ${of}`),
  km: (km: number, lang: Lang) => (lang === 'bn' ? `${num(km, lang)} কিমি` : `${km} km`),
  mm: (mm: number, lang: Lang) => (lang === 'bn' ? `${num(mm, lang)} মিমি` : `${mm} mm`),
  approvedBy: (name: string, iso: string, lang: Lang) =>
    lang === 'bn' ? `যাচাই করেছেন: ${name}, ${when(iso, lang)}` : `Verified by ${name}, ${when(iso, lang)}`,
};

/** Bangla names of stations and upazilas shown on screen. */
export const STATION_BN: Record<string, string> = { Kazipur: 'কাজীপুর', Sirajganj: 'সিরাজগঞ্জ', 'Sirajganj Sadar': 'সিরাজগঞ্জ সদর', Sariakandi: 'সারিয়াকান্দি', Dhunat: 'ধুনট', Belkuchi: 'বেলকুচি', Chauhali: 'চৌহালি', Gabtali: 'গাবতলী', Kalihati: 'কালিহাতী', 'Ullah Para': 'উল্লাপাড়া', Bhuapur: 'ভূঞাপুর', Gopalpur: 'গোপালপুর', Sherpur: 'শেরপুর' }; // NEW entries after Chauhali need a native check
