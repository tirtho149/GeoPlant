export const meta = {
  name: 'disease-label-judge',
  description: 'SAGE two-layer crop/disease label quality check (Layer1 crop validity + Layer2 disease judge)',
  phases: [ { title: 'Judge' } ],
}

const CROPS = [{"crop": "Alfalfa", "diseases": ["Downy Mildew", "Stemphylium Leaf Spot", "Summer Black Stem"]}, {"crop": "Almond", "diseases": ["Brown Rot", "Stigmina Fungus"]}, {"crop": "American Beech", "diseases": ["Beech Leaf Disease", "Neonectria Coccinea"]}, {"crop": "Apple", "diseases": ["Apple Scab", "Black Rot", "Blue Mold", "Cedar-Apple Rust", "Fire Blight"]}, {"crop": "Aspen/Poplar", "diseases": ["Cytospora Cankers", "Marssonina Leaf Spots"]}, {"crop": "Balsam Fir", "diseases": ["Fir-Fern Rust", "Rhizosphaera Needle Cast"]}, {"crop": "Blue Spruce", "diseases": ["Ceropsora Weirii", "Rhizosphaera Needle Cast", "Spruce Needle Rusts"]}, {"crop": "Boxwood", "diseases": ["Boxwood Blight", "Pseudonectria Buxi B.O. Dodge"]}, {"crop": "Burley Tobacco", "diseases": ["Blue Mold", "Rhizoctonia Damping-Off, Blight And Rot", "Tomato Spotted Wilt Virus"]}, {"crop": "Cabbage", "diseases": ["Bacterial Soft Rot", "Black Rot Of Crucifers", "Club Root Of Crucifers", "Downy Mildew", "Phytophthora Root And Stem Rot"]}, {"crop": "Common Bean", "diseases": ["Beet Curly Top Virus", "Common Bacterial  Blight Of Beans, Fuscous Blight", "Dry Bean Rust", "Halo Blight", "Sclerotinia Timber Rot"]}, {"crop": "Common Lilac", "diseases": ["Anthracnose", "Cladosporium Fungi"]}, {"crop": "Common Sunflower", "diseases": ["Rust", "Sclerotinia Timber Rot"]}, {"crop": "Corn", "diseases": ["Anthracnose", "Bacterial Rot And Blight", "Brown Spot Of Corn", "Common Corn Rust", "Corn Smut", "Downy Mildew", "Dry Rot Of Ears And Stalks Of Maize", "Fusarium Graminearum Schwabe", "Goss' Bacterial Wilt", "Gray Leaf Spot", "Northern Corn Leaf Blight", "Southern Corn Rust", "White Ear Rot And Seedling Blight Of Maize", "Xanthomonas Vasicola"]}, {"crop": "Creeping Bentgrass", "diseases": ["Anthracnose", "Dollar Spot"]}, {"crop": "Cucumber", "diseases": ["Angular Leaf Spot Of Cucumber", "Anthracnose", "Bacterial Wilt", "Corynespora Leaf Spot", "Cucurbit Downy Mildew", "Gummy Stem Blight", "Phytophthora Blight", "Powdery Mildew", "Pythium Diseases", "Rhizoctonia Damping-Off, Blight And Rot", "Scab"]}, {"crop": "Cultivated Garlic", "diseases": ["Alternaria Embellisia Togashi", "Bread Mold", "Gray Molds", "Onion Rust", "White Rot"]}, {"crop": "Dogwood", "diseases": ["Dogwood Anthracnose", "Powdery Mildew"]}, {"crop": "Douglas-Fir", "diseases": ["Rhabdocline Needlecasts", "Swiss Needle Cast"]}, {"crop": "Eastern White Pine", "diseases": ["Caliciopsis Canker", "Needle Cast", "Stem Rot", "White Pine Blister Rust"]}, {"crop": "Eggplant", "diseases": ["Diaporthe Vexans Gratz", "Phytophthora Blight"]}, {"crop": "Elm", "diseases": ["Bacterial Leaf Scorch", "Black Spot Of Elm", "Dutch Elm Disease"]}, {"crop": "Garden Onion", "diseases": ["Black Mold", "Downy Mildew", "Fusarium Damping-Off", "Iris Yellow Spot Virus", "Onion Yellows Phytoplasma", "Purple Blotch"]}, {"crop": "Gourd", "diseases": ["Fusarium Damping-Off", "Phytophthora Blight", "Powdery Mildew"]}, {"crop": "Grape", "diseases": ["Black Rot", "Downy Mildew", "Grape Anthracnose", "Gray Mold", "Powdery Mildew", "Pseudocercospora Leaf Spot"]}, {"crop": "Highbush Blueberry", "diseases": ["Anthracnose", "Blueberry Leaf Rust", "Diaporthe Vaccinii Shear", "Mummy Berry", "Phomopsis Cankers And Twig Blights", "Twig Canker"]}, {"crop": "Hops", "diseases": ["Apple Mosaic Virus", "Fusarium Wilts, Blights, Rots And Damping-Off", "Powdery Mildew"]}, {"crop": "Hosta", "diseases": ["Hosta Virus X", "Southern Blight", "Tobacco Rattle Virus"]}, {"crop": "Hydrangea", "diseases": ["Cercospora Fungi", "Gray Molds"]}, {"crop": "Juniper", "diseases": ["Diaporthe Juniperivora Sacc.", "Kabatina Blight", "Needle Cast", "Pestalotiopsis Leaf Spot", "Phomopsis Cankers And Twig Blights"]}, {"crop": "Lemon", "diseases": ["Green Mold", "Whisker Mold"]}, {"crop": "Lettuce", "diseases": ["Cercospora Leaf Spot", "Downy Mildew", "Gray Mold", "Lettuce Chlorosis Virus", "Mirafiori Lettuce Big-Vein Virus", "Powdery Mildew", "Rhizoctonia Damping-Off, Blight And Rot", "Sclerotinia Stem Rot", "Sclerotinia Timber Rot", "Southern Blight", "Tomato Spotted Wilt Virus"]}, {"crop": "Loblolly Pine", "diseases": ["Leptographium Root Disease", "Pine Needle Rusts", "Wood Decay Fungi"]}, {"crop": "Maple", "diseases": ["Anthracnose", "Maple Cankers", "Tar Spot Of Maple"]}, {"crop": "Melon", "diseases": ["Alternaria Leaf Blight", "Anthracnose", "Bacterial Fruit Blotch", "Bacterial Wilt", "Charcoal Rot", "Cucurbit Downy Mildew", "Fusarium Wilts, Blights, Rots And Damping-Off", "Gummy Stem Blight", "Monosporascus Root Rot", "Phytophthora Blight", "Powdery Mildew", "Pythium Diseases", "Sour Rot"]}, {"crop": "Norway Maple", "diseases": ["Anthracnose", "Cristulariella Leaf Spot"]}, {"crop": "Oak", "diseases": ["Anthracnose", "Bacterial Leaf Scorch", "Botryosphaeria Rots And Cankers", "Coryneum Twig Blight", "Cytospora Cankers", "Ganoderma Root And Butt Rot", "Leaf Spot", "Monochaetia Fungi", "Nectria Canker", "Oak Leaf Blister", "Oak Wilt", "Polypore Fungus"]}, {"crop": "Peach", "diseases": ["Botryosphaeria Canker, White Rot", "Brown Rot", "Cladosporium Fungi", "Peach Leaf Curl", "Peach Mosaic Virus", "Stigmina Fungus"]}, {"crop": "Peanut", "diseases": ["Nothopassalora Personata", "Passalora Fungus", "Southern Blight"]}, {"crop": "Pecan", "diseases": ["Diplodia Fungus", "Pecan Scab"]}, {"crop": "Peony", "diseases": ["Anthracnose", "Botrytis Blight", "Phytophthora Crown Rot"]}, {"crop": "Pepper", "diseases": ["Alternaria Black Molds / Stem Cankers", "Bacterial Spot", "Bitter Rot And Anthracnose", "Blossom End Rot", "Phytophthora Blight", "Southern Blight", "Tomato Spotted Wilt Virus"]}, {"crop": "Phlox", "diseases": ["Downy Mildew", "Powdery Mildew", "Root, Stem, And Crown Rots"]}, {"crop": "Plum and Cherry", "diseases": ["Black Knot", "Blumeriella Leaf Spot Of Cherry And Plum", "Brown Rots", "Phloeosporella Fungus", "Powdery Mildew", "Rust"]}, {"crop": "Potato", "diseases": ["Bacterial Soft Rot", "Early Blight", "Fusarium Wilts, Blights, Rots And Damping-Off", "Late Blight", "Phytophthora Root And Stem Rot", "Rhizoctonia Damping-Off, Blight And Rot", "Tomato Spotted Wilt Virus"]}, {"crop": "Red Pine", "diseases": ["Annosum Root Disease", "Diplodia Sapinea De Not.", "Sirococcus Blight Of Conifers"]}, {"crop": "Rhododendrons And Azaleas", "diseases": ["Guignardia Blotch", "Leaf And Flower Gall", "Pestalotiopsis Leaf Spot"]}, {"crop": "Rice", "diseases": ["Bacterial Panicle Blight", "Narrow Brown Leaf Spot", "Rhizoctonia Damping-Off, Blight And Rot", "Rice Blast Disease"]}, {"crop": "Rose", "diseases": ["Black Spot", "Powdery Mildew", "Rose Rosette Virus"]}, {"crop": "Soybean", "diseases": ["Bacterial Blight", "Bacterial Pustule Of Soybean Disease", "Bean Pod Mottle Virus", "Brown Stem Rot", "Cercospora Blight", "Charcoal Rot", "Downy Mildew", "Frogeye Leaf Spot", "Genus Diaporthe", "Rhizoctonia Damping-Off, Blight And Rot", "Root And Stem Rot", "Sclerotinia Timber Rot", "Septoria Leaf Spot", "Southern Blight", "Soybean Rust", "Soybean Vein Necrosis Virus", "Taproot Decline On Soybean"]}, {"crop": "Spinach", "diseases": ["Cladosporium Leaf Spot", "Downy Mildew", "White Rust"]}, {"crop": "Squash", "diseases": ["Anthracnose", "Choanephora Fruit Rot", "Cucurbit Downy Mildew", "Fusarium Wilts, Blights, Rots And Damping-Off", "Gummy Stem Blight", "Phytophthora Blight", "Plectosphaerella Fungus", "Powdery Mildew", "Pythium Diseases", "Southern Blight"]}, {"crop": "St. Augustinegrass", "diseases": ["Rhizoctonia Damping-Off, Blight And Rot", "Sugarcane Mosaic Virus"]}, {"crop": "Strawberry", "diseases": ["Angular Leaf Spot Of Strawberry", "Anthracnose", "Gray Mold", "Leaf Spot", "Phomopsis Leaf Blight And Fruit Rot", "Ramularia Grevilleana Verkley & U. Braun"]}, {"crop": "Sugar Beet", "diseases": ["Beet Necrotic Yellow Vein Virus", "Cercospora Leaf Spot", "Powdery Mildew"]}, {"crop": "Sweet Potato", "diseases": ["Bacteria Wilt And Soft Rot", "Black Rot", "Bread Mold", "Charcoal Rot", "Fusarium Damping-Off", "Fusarium Lateritium Nees", "Fusarium Root Rot And Wilt", "Fusarium Wilt", "Java Black Rot", "Penicillium Fungi", "Pythium Root And Stem Rot", "Rhizopus Soft Rots", "Scurf", "Sour Rot", "Southern Blight", "Streptomyces Soil Rot", "Sweet Potato Feathery Mottle Virus"]}, {"crop": "Tomato", "diseases": ["Anthracnose", "Bacterial Canker And Wilt Of Tomato", "Bacterial Speck Of Tomato", "Bacterial Wilt", "Cucumber Mosaic Virus", "Early Blight", "Gray Mold", "Gray Molds", "Late Blight", "Phytophthora Blight", "Rhizopus Soft Rots", "Sclerotinia Timber Rot", "Septoria Leaf Spot", "Southern Bacterial Wilt", "Southern Blight", "Tomato Leaf Mould", "Tomato Spotted Wilt Virus", "Verticillium Wilts"]}, {"crop": "Watermelon", "diseases": ["Anthracnose", "Bacterial Fruit Blotch", "Blossom End Rot", "Cucurbit Downy Mildew", "Cucurbit Yellow Vine Decline", "Gummy Stem Blight", "Phytophthora Blight", "Powdery Mildew", "Pythium Diseases", "Southern Blight", "Unknown Virus", "Watermelon Mosaic Virus"]}, {"crop": "Wheat", "diseases": ["Barley Yellow Dwarf Virus", "Dwarf Bunt, Dwarf Smut", "Fusarium Graminearum Schwabe", "Fusarium Wilts, Blights, Rots And Damping-Off", "Karnal Bunt", "Loose Smut Of Wheat Or Barley", "Parastagonospora Nodorum", "Powdery Mildew", "Stripe Rust", "Tan Spot", "Wheat Leaf Rust", "Wheat Stem Rust", "Wheat Streak Mosaic Virus", "Zymoseptoria Tritici"]}, {"crop": "Witch-Hazel", "diseases": ["Gonatobotryum Fungus", "Phyllosticta Leaf Spots"]}]
const CROP_PROMPT = "You are an expert agronomist. Apply the decision tree below to the crop name given.\n\nDECISION TREE:\n  Node A: Is this entry a real plant or plant-based crop (not a spreadsheet label, number, or non-plant)?\n    -> NO  -> verdict: INVALID\n    -> YES -> Node B\n  Node B: Is it grown as an agricultural or horticultural crop (food, fibre, spice, timber, ornamental)?\n    -> NO  -> verdict: NON_CROP\n    -> YES -> Node C\n  Node C: Is the common crop name spelled correctly and reasonably standardised?\n    -> NO  -> verdict: MISSPELLED_OR_UNSTANDARDISED\n    -> YES -> verdict: VALID"
const DIS_PROMPT = "You are an expert plant pathologist. Quality-check disease labels for the crop below.\n\nVerdict rules:\n  CORRECT      - well-documented disease known to affect this crop.\n  INCORRECT    - wrong crop; disease of a completely different plant; or entry is not a disease at all.\n  QUESTIONABLE - real disease but label is vague, misspelled, names a pathogen genus instead of a\n                 disease, refers to an insect pest or beneficial organism, or is an unusual\n                 / unverified association with this crop."

const SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['crop','crop_validation','disease_check'],
  properties: {
    crop: { type: 'string' },
    crop_validation: {
      type: 'object', additionalProperties: false,
      required: ['node_a','node_b','node_c','verdict','canonical_name','category','notes'],
      properties: {
        node_a: { type: 'string', enum: ['YES','NO'] },
        node_b: { type: 'string', enum: ['YES','NO','N/A'] },
        node_c: { type: 'string', enum: ['YES','NO','N/A'] },
        verdict: { type: 'string', enum: ['VALID','INVALID','NON_CROP','MISSPELLED_OR_UNSTANDARDISED'] },
        canonical_name: { type: 'string' },
        category: { type: 'string' },
        notes: { type: 'string' },
      },
    },
    disease_check: {
      type: 'object', additionalProperties: false,
      required: ['disease_verdicts','similar_groups','summary'],
      properties: {
        disease_verdicts: { type: 'array', items: {
          type: 'object', additionalProperties: false,
          required: ['disease','verdict','reason'],
          properties: {
            disease: { type: 'string' },
            verdict: { type: 'string', enum: ['CORRECT','INCORRECT','QUESTIONABLE'] },
            reason: { type: 'string' },
          } } },
        similar_groups: { type: 'array', items: {
          type: 'object', additionalProperties: false,
          required: ['diseases','reason'],
          properties: {
            diseases: { type: 'array', items: { type: 'string' } },
            reason: { type: 'string' },
          } } },
        summary: { type: 'string' },
      },
    },
  },
}

function prompt(c) {
  const dl = c.diseases.map((d) => `- ${d}`).join('\n')
  return `${CROP_PROMPT}\n\nThen, for the SAME crop:\n\n${DIS_PROMPT}\n\n`
    + `Crop to evaluate: ${c.crop}\n\nDiseases:\n${dl}\n\n`
    + `Return the combined JSON object with crop, crop_validation (Layer 1), and disease_check (Layer 2).`
}

const out = await parallel(CROPS.map((c) => () =>
  agent(prompt(c), { label: `judge:${c.crop}`, phase: 'Judge', schema: SCHEMA })
    .then((r) => ({ ...r, crop: c.crop }))
    .catch(() => null)))

const results = out.filter(Boolean)
const inc = results.reduce((n, r) => n + (r.disease_check?.disease_verdicts || []).filter((v) => v.verdict === 'INCORRECT').length, 0)
const q = results.reduce((n, r) => n + (r.disease_check?.disease_verdicts || []).filter((v) => v.verdict === 'QUESTIONABLE').length, 0)
log(`judged ${results.length} crops; INCORRECT=${inc} QUESTIONABLE=${q}`)
return { n: results.length, results }
