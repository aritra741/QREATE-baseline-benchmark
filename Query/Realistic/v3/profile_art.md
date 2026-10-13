# Data profile: art

Tables (rows = documents): art (1000)

Columns marked INITIAL are read by the initial build; build questions may use ONLY those. Test questions may use any column.

Value statistics are from the correct data (what a perfect extraction would hold). Values containing '||' are lists.

## art.age  [INITIAL; number; filled 751/1000; distinct 103]
description: age of the artist (if death_date is given, compute as death_date - birth_date; otherwise, compute as 2025/1/1 - birth_date)
most common values: '76' x24; '77' x24; '83' x24; '75' x22; '82' x21; '78' x20; '71' x20; '70' x20; '73' x19; '85' x19

## art.art_institution  [INITIAL; list; filled 709/1000; distinct 645]
description: art academies, schools, organizations, associations, or exhibition societies the artist was affiliated with, taught at, or participated in (e.g., national art academies, artist unions, art schools, exhibition societies).
most common values: 'Royal Academy of Arts (RA), London, UK' x6; 'Royal Academy of Arts' x5; 'Self-taught' x5; 'école des Beaux-Arts' x4; 'Real Academia de Bellas Artes de San Fernando' x4; 'Art Students League of New York' x4; 'Imperial Academy of Arts, Saint Petersburg, Russia' x4; 'Academy of San Carlos' x3; 'Hochschule für bildende Künste Hamburg' x3; 'Slade School of Fine Art' x3

## art.art_movement  [INITIAL; list; filled 778/1000; distinct 471]
description: art movement contributed to (e.g., impressionism)
most common values: 'Surrealism' x30; 'Abstract Expressionism' x28; 'Realism' x22; 'Pop Art' x18; 'Impressionism' x16; 'Contemporary' x14; 'Abstract' x13; 'Expressionism' x13; 'Minimalism' x11; 'Romanticism' x11

## art.awards  [new; number; filled 1000/1000; distinct 11]
description: Number of significant and clearly documented awards the artist received (enter an integer; use 0 if none; exclude medals, scholarships, or honorary mentions).
most common values: '0' x838; '1' x91; '2' x33; '3' x14; '4' x13; '5' x3; '6' x3; '7' x2; '50' x1; '8' x1

## art.birth_city  [new; list; filled 936/1000; distinct 652]
description: city where the artist was born
most common values: 'Paris' x30; 'London' x23; 'New York City' x16; 'New York' x13; 'Philadelphia' x12; 'Chicago' x10; 'Berlin' x9; 'Boston' x8; 'Brooklyn' x7; 'Istanbul' x6

## art.birth_continent  [INITIAL; category; filled 980/1000; distinct 7]
description: continent where the artist was born, select one from [Africa, Asia, Europe, North America, South America, Oceania]
most common values: 'Europe' x529; 'North America' x303; 'Asia' x79; 'South America' x34; 'Africa' x19; 'Oceania' x14; 'Australia' x2

## art.birth_country  [INITIAL; list; filled 977/1000; distinct 100]
description: country where the artist was born (e.g., netherlands)
most common values: 'United States' x245; 'France' x94; 'United Kingdom' x86; 'Germany' x66; 'Italy' x39; 'Japan' x25; 'Canada' x24; 'Spain' x15; 'Romania' x15; 'Mexico' x14

## art.birth_date  [new; free text; filled 978/1000; distinct 938]
description: date in %Y/%-m/%-d format (e.g., 1839/1/9), or leave empty if not applicable
most common values: '1905/4/28' x4; '1905/4/27' x4; '1905/4/22' x3; '1905/4/19' x3; '1905/4/23' x3; '1905/4/29' x3; '1905/5/14' x2; '1905/4/25' x2; '1905/5/15' x2; '1905/5/12' x2

## art.century  [new; free text; filled 709/1000; distinct 4]
description: century when the artist was active or influential (e.g., 19th or 19th–20th; can span multiple centuries)
most common values: '19th-20th' x332; '20th' x167; '20th-21st' x166; '19th' x44

## art.color  [INITIAL; list; filled 953/1000; distinct 254]
description: the dominant or characteristic colors of the image (e.g., red and black, muted earth tones, bright multicolored palette, monochrome blue). Describe the color usage in free-form text; if multiple color groups are important, separate them with `||`.
most common values: 'Earth Tones' x151; 'Blue' x85; 'Green' x64; 'Red' x58; 'Black And White' x50; 'Brown' x38; 'Yellow' x27; 'Multicolored' x24; 'White' x18; 'Neutral Tones' x14

## art.composition  [new; free text; filled 953/1000; distinct 368]
description: the way visual elements are arranged in the image (e.g., asymmetrical with central focus, symmetrical and balanced, dynamic diagonal composition, crowded and layered, minimal with large negative space). Describe the composition style in one short free-form phrase.
most common values: 'Balanced' x87; 'Asymmetrical' x83; 'Centralized' x47; 'Dynamic' x47; 'Symmetrical' x45; 'Central Focus' x31; 'Geometric' x29; 'Centered' x19; 'Geometric Arrangement' x16; 'Minimalist' x16

## art.death_city  [new; free text; filled 559/1000; distinct 292]
description: city where the artist died, or leave empty if not applicable
most common values: 'Paris' x58; 'New York' x34; 'London' x33; 'New York City' x27; 'Mexico City' x11; 'Philadelphia' x8; 'Rome' x7; 'Los Angeles' x7; 'Tokyo' x7; 'Saint Petersburg' x6

## art.death_country  [INITIAL; free text; filled 628/1000; distinct 61]
description: country where the artist died, or leave empty if not applicable (e.g., switzerland)
most common values: 'United States' x179; 'France' x103; 'United Kingdom' x66; 'Italy' x32; 'Germany' x28; 'Switzerland' x17; 'Mexico' x16; 'Japan' x14; 'Australia' x13; 'Canada' x11

## art.death_date  [new; free text; filled 762/1000; distinct 751]
description: date in %Y/%-m/%-d format (e.g., 1836/1/1), or leave empty if not applicable
most common values: '1905/6/3' x2; '2005/4/22' x2; '1905/5/13' x2; '1986/1/1' x2; '1963/4/9' x2; '2011/4/8' x2; '1935/4/15' x2; '1905/7/7' x2; '1969/3/14' x2; '1962/1/16' x2

## art.field  [new; list; filled 1000/1000; distinct 463]
description: primary artistic field, choose one or more from: [Painting, Sculpture, Printmaking, Drawing, Photography, Illustration, Collage, Textile art, Installation, Performance, Ceramics, Digital art, Architecture, Mosaic, Graphic Design, Calligraphy], seperated by `||` (e.g. Collage || Illustration || Textile art).
most common values: 'Painting' x309; 'Painting||Sculpture' x37; 'Painting||Printmaking' x32; 'Sculpture' x27; 'Photography' x22; 'Painting||Illustration' x17; 'Painting||Writing' x11; 'Sculpture||Painting' x9; 'Painting||Drawing' x8; 'Painting||Photography' x7

## art.genre  [INITIAL; list; filled 680/1000; distinct 450]
description: primary genre of work, choose one or more from: [Portrait, Landscape, Still Life, Religious, Mythological, History, genre, Nude, Animal, Illustration, Allegorical, Abstract, Fantasy, Sketch, Figurative, Conceptual, Surrealist, Symbolic, Political, Social Realism, Pop art, Narrative, Environmental, Sculpture, Architecture, Music, Film, Digital art, Literature, Other], seperated by `||` (e.g. Portrait || Political).
most common values: 'Abstract' x62; 'Landscape' x43; 'Portrait' x38; 'Figurative' x13; 'Portrait||Landscape' x13; 'Landscape||Portrait' x8; 'Surrealism' x6; 'Avant-garde' x4; 'Landscape||Abstract' x4; 'Realism' x4

## art.image_genre  [INITIAL; list; filled 883/1000; distinct 65]
description: the artistic genre or type of the image, described in a short phrase (e.g., landscape, portrait, still life, historical scene, narrative scene, conceptual work). Use free-form text; if multiple genres are relevant, separate them with `||`.
most common values: 'Portrait' x224; 'Landscape' x158; 'Still Life' x99; 'Abstract' x75; 'Sculpture' x46; 'Figurative' x46; 'Genre Painting' x42; 'Historical' x16; 'Geometric' x15; 'Installation' x14

## art.marriage  [INITIAL; category; filled 295/1000; distinct 7]
description: marital status of the artist, reflecting the artist’s latest (final) marital status as mentioned in the biography. Choose one from: [Cohabiting, Divorced, Married, Remarried, Separated, Unmarried, Widowed]. Only extract and fill in the last marital status referenced in the text.
most common values: 'Married' x196; 'Unmarried' x40; 'Remarried' x28; 'Divorced' x13; 'Widowed' x12; 'Separated' x4; 'Cohabiting' x2

## art.name  [INITIAL; free text; filled 999/1000; distinct 996]
description: full name of the artist
most common values: 'Oscar Agustín Alejandro Schulz Solari' x2; 'Ben Shahn' x2; 'Oswald Achenbach' x2; 'Nicolas Carone' x1; 'Eduardo Chillida Juantegui' x1; 'Konstantin Yegorovich Makovsky' x1; 'Anne Wardrope (Nott) Brigman' x1; 'Gerhard Richter' x1; 'Peter Dreher' x1; 'Alfred Julio Jensen' x1

## art.nationality  [new; list; filled 989/1000; distinct 201]
description: artist's nationality (e.g., french, japanese)
most common values: 'American' x254; 'French' x86; 'British' x80; 'German' x48; 'Italian' x33; 'Japanese' x26; 'Russian' x20; 'Australian' x16; 'Canadian' x15; 'Brazilian' x14

## art.object  [new; list; filled 924/1000; distinct 746]
description: the primary visible objects or subjects depicted in the image (e.g., woman, tree, city skyline, animals, abstract shapes). List the key visual elements as nouns or short noun phrases; if there are several, separate them with `||`.
most common values: 'Geometric Shapes' x32; 'Human Figure' x22; 'Human Figures' x17; 'Shapes' x11; 'Geometric Forms' x8; 'Seated Person' x7; 'People' x7; 'Person' x6; 'Human Face' x6; 'Two People' x5

## art.style  [INITIAL; list; filled 957/1000; distinct 112]
description: the overall artistic style of the image, described in a short phrase (e.g., abstract expressionism, geometric abstraction, minimalist line drawing). Use free-form text; if multiple styles are clearly present, separate them with `||`.
most common values: 'Expressionism' x70; 'Romanticism' x62; 'Conceptual Art' x52; 'Abstract Expressionism' x49; 'Impressionism' x47; 'Realism' x45; 'Surrealism' x39; 'Pop Art' x31; 'Art Nouveau (Modern)' x30; 'Minimalism' x30

## art.teaching  [INITIAL; number; filled 1000/1000; distinct 2]
description: whether the artist taught at an institution (1 if yes, 0 if none)
most common values: '0' x816; '1' x184

## art.theme  [new; free text; filled 0/1000; distinct 0]
description: the main idea, message, or subject matter conveyed by the image (e.g., nature, war, love, spirituality, identity, urban life, social criticism). Describe it briefly in free-form text, not limited to any fixed list.
most common values: 

## art.tone  [INITIAL; free text; filled 953/1000; distinct 27]
description: the overall tonal and emotional quality of the image (e.g., bright and cheerful, dark and dramatic, calm and neutral, cold and somber). Use a short free-form description that captures both visual tone and mood.
most common values: 'Neutral' x456; 'Bright' x215; 'Dark' x187; 'Warm' x31; 'Soft' x19; 'Light' x10; 'Muted' x4; 'Bold' x3; 'Dynamic' x3; 'Vibrant' x3

## art.zodiac  [INITIAL; category; filled 863/1000; distinct 11]
description: western zodiac sign based on birth date, choose only one from [Aries, Taurus, Gemini, Cancer, Leo, Virgo, Libra, Scorpio, Sagittarius, Capricorn, Aquarius, Pisces]
most common values: 'Aries' x105; 'Taurus' x98; 'Pisces' x91; 'Gemini' x85; 'Leo' x81; 'Aquarius' x77; 'Sagittarius' x73; 'Scorpio' x67; 'Virgo' x65; 'Libra' x62
