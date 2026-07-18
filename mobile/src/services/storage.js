import AsyncStorage from '@react-native-async-storage/async-storage';

const PROFILE_KEY = 'vietnexus.profile.v1';
const RECEIVED_CARDS_KEY = 'vietnexus.receivedCards.v1';

export async function loadProfile() {
  try {
    const raw = await AsyncStorage.getItem(PROFILE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

export async function saveProfile(profile) {
  try {
    await AsyncStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  } catch (e) {
    // storage unavailable — profile stays in-memory for this session
  }
}

export async function loadReceivedCards() {
  try {
    const raw = await AsyncStorage.getItem(RECEIVED_CARDS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}

export async function addReceivedCard(card) {
  const list = await loadReceivedCards();
  const next = [{ ...card, receivedAt: Date.now() }, ...list.filter((c) => c.name !== card.name)].slice(0, 30);
  try {
    await AsyncStorage.setItem(RECEIVED_CARDS_KEY, JSON.stringify(next));
  } catch (e) {
    // storage unavailable — this run's scan still returns in-memory
  }
  return next;
}
